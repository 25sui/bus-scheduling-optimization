"""
LSTM客流预测模型

基于PyTorch实现的LSTM时序预测模型，用于公交客流的短期预测。
网络结构：2层LSTM + Dropout + 全连接输出
"""
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.config import LSTM_CONFIG


class PassengerFlowDataset(Dataset):
    """PyTorch Dataset for passenger flow prediction"""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class LSTMPredictor(nn.Module):
    """
    LSTM客流预测模型

    Architecture:
        Input(seq_len, n_features)
          -> 2xLSTM(hidden_size=128, dropout=0.2)
          -> FC(hidden_size, output_size)
    """

    def __init__(self, input_size: int = None, hidden_size: int = None,
                 num_layers: int = None, output_size: int = None,
                 dropout: float = None):
        super().__init__()

        cfg = LSTM_CONFIG.copy()
        input_size = input_size or len([k for k in [
            "hour", "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            "is_morning_peak", "is_evening_peak", "is_peak",
            "is_weekend"
        ]])  # 实际特征数由数据决定
        # 注意：实际 input_size 应在训练前根据特征矩阵动态设置
        self.input_size = input_size or cfg["input_size"]
        self.hidden_size = hidden_size or cfg["hidden_size"]
        self.num_layers = num_layers or cfg["num_layers"]
        self.output_size = output_size or cfg["output_size"]

        self.lstm = nn.LSTM(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            batch_first=True,
            dropout=dropout or cfg["dropout"],
        )
        self.fc = nn.Linear(self.hidden_size, self.output_size)
        self._init_weights()

    def _init_weights(self):
        """Xavier初始化"""
        for name, param in self.named_parameters():
            if "weight_ih" in name:
                nn.init.xavier_uniform_(param.data)
            elif "weight_hh" in name:
                nn.init.orthogonal_(param.data)
            elif "bias" in name:
                param.data.fill_(0)

    def forward(self, x):
        """
        Args:
            x: (batch_size, seq_len, input_size)
        Returns:
            out: (batch_size, output_size) 预测的客流值
        """
        lstm_out, (h_n, c_n) = self.lstm(x)
        # 取最后一个时间步的隐藏状态
        last_hidden = lstm_out[:, -1, :]
        out = self.fc(last_hidden)
        return out


def train_model(model: LSTMPredictor, train_loader: DataLoader,
                val_loader: DataLoader, device: torch.device,
                epochs: int = None, lr: float = None,
                patience: int = None) -> dict:
    """
    训练LSTM模型

    Returns:
        history: 训练历史（loss曲线）
    """
    cfg = LSTM_CONFIG.copy()
    epochs = epochs or cfg["num_epochs"]
    learning_rate = lr or cfg["learning_rate"]
    patience = patience or cfg["patience"]

    model = model.to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    history = {"train_loss": [], "val_loss": []}
    best_val_loss = float("inf")
    best_state_dict = None
    counter = 0

    for epoch in range(epochs):
        # Training phase
        model.train()
        train_losses = []
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(loss.item())

        avg_train_loss = np.mean(train_losses)

        # Validation phase
        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y)
                val_losses.append(loss.item())

        avg_val_loss = np.mean(val_losses)
        scheduler.step(avg_val_loss)

        history["train_loss"].append(avg_train_loss)
        history["val_loss"].append(avg_val_loss)

        if (epoch + 1) % 10 == 0:
            current_lr = optimizer.param_groups[0]["lr"]
            print(f"  Epoch {epoch+1}/{epochs} | "
                  f"Train Loss: {avg_train_loss:.4f} | "
                  f"Val Loss: {avg_val_loss:.4f} | "
                  f"LR: {current_lr:.6f}")

        # Early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            best_state_dict = model.state_dict().copy()
            counter = 0
        else:
            counter += 1
            if counter >= patience:
                print(f"  Early stopping at epoch {epoch+1}")
                break

    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    return history


def evaluate_model(model: LSTMPredictor, test_loader: DataLoader,
                   device: torch.device) -> dict[str, float]:
    """
    评估模型性能

    Returns:
        metrics: 包含 MAE, RMSE, MAPE 的字典
    """
    model.eval()
    predictions, actuals = [], []

    with torch.no_grad():
        for batch_x, batch_y in test_loader:
            batch_x = batch_x.to(device)
            preds = model(batch_x).cpu().numpy()
            actuals.extend(batch_y.numpy())
            predictions.extend(preds)

    y_true = np.array(actuals).flatten()
    y_pred = np.array(predictions).flatten()

    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) / np.clip(y_true, 1e-5, None))) * 100

    metrics = {
        "MAE": round(mae, 3),
        "RMSE": round(rmse, 3),
        "MAPE": round(mape, 2),
    }
    print(f"[评估] MAE={mae:.2f}, RMSE={rmse:.2f}, MAPE={mape:.2f}%")
    return metrics


if __name__ == "__main__":
    print("[LSTM模型] 模块加载成功")
    print(f"  配置: {LSTM_CONFIG}")
