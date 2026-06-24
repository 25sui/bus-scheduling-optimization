"""
模型训练主流程

执行LSTM和XGBoost模型的训练、评估与对比。
生成模型文件和评估报告。
"""
import numpy as np
import pandas as pd
import torch
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.config import PROCESSED_DATA_DIR, MODEL_DIR, LSTM_CONFIG, TEST_RATIO
from src.data.preprocess import DataPreprocessor
from src.prediction.lstm_model import (
    LSTMPredictor, PassengerFlowDataset,
    train_model, evaluate_model, DataLoader
)
from src.prediction.xgboost_model import XGBoostPredictor


def main():
    """训练主流程"""
    print("=" * 60)
    print("公交客流预测模型 — 训练流程")
    print("=" * 60)

    # 加载数据
    data_path = PROCESSED_DATA_DIR / "processed_data.csv"
    if not data_path.exists():
        print("[错误] 未找到预处理数据，请先运行 preprocess.py")
        return

    df = pd.read_csv(data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    print(f"[数据] 加载 {len(df)} 条预处理记录")

    # 预处理
    preprocessor = DataPreprocessor()
    processed_df = preprocessor.fit_transform(df)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[设备] 使用 {device}")

    # ========== 训练 LSTM ==========
    print("\n" + "-" * 40)
    print("[1/2] 训练 LSTM 模型...")
    print("-" * 40)

    X_lstm, y_lstm = preprocessor.create_sequences(processed_df)
    n_features = X_lstm.shape[2]  # 动态特征维度
    print(f"LSTM 样本: {X_lstm.shape}, 特征数: {n_features}")

    datasets = preprocessor.split_dataset(X_lstm, y_lstm)
    train_data = datasets["train"]
    val_data = datasets["val"]
    test_data = datasets["test"]

    train_ds = PassengerFlowDataset(train_data[0], train_data[1])
    val_ds = PassengerFlowDataset(val_data[0], val_data[1])
    test_ds = PassengerFlowDataset(test_data[0], test_data[1])

    train_loader = DataLoader(train_ds, batch_size=LSTM_CONFIG["batch_size"], shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=LSTM_CONFIG["batch_size"])
    test_loader = DataLoader(test_ds, batch_size=LSTM_CONFIG["batch_size"])

    lstm_model = LSTMPredictor(input_size=n_features)
    history = train_model(lstm_model, train_loader, val_loader, device)
    lstm_metrics = evaluate_model(lstm_model, test_loader, device)

    # 保存LSTM模型
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    lstm_path = MODEL_DIR / "lstm_predictor.pth"
    torch.save({
        "model_state_dict": lstm_model.state_dict(),
        "input_size": n_features,
        "config": LSTM_CONFIG,
        "history": history,
    }, lstm_path)
    print(f"[保存] LSTM模型 → {lstm_path}")

    # ========== 训练 XGBoost ==========
    print("\n" + "-" * 40)
    print("[2/2] 训练 XGBoost 基线模型...")
    print("-" * 40)

    y_xgb, X_xgb = preprocessor.create_xgboost_features(processed_df)

    from sklearn.model_selection import train_test_split as split

    X_train_xgb, X_test_xgb, y_train_xgb, y_test_xgb = split(
        X_xgb, y_xgb, test_size=TEST_RATIO, random_state=42
    )
    X_val_xgb = X_train_xgb.iloc[:int(len(X_train_xgb) * 0.15)]
    y_val_xgb = y_train_xgb.iloc[:int(len(y_train_xgb) * 0.15)]

    xgb_model = XGBoostPredictor()
    xgb_model.fit(X_train_xgb, y_train_xgb, X_val_xgb, y_val_xgb)
    xgb_pred = xgb_model.predict(X_test_xgb)
    xgb_metrics = xgb_model.evaluate(y_test_xgb.values, xgb_pred)

    # 保存XGBoost模型
    import joblib
    xgb_path = MODEL_DIR / "xgboost_predictor.joblib"
    joblib.dump(xgb_model, xgb_path)
    print(f"[保存] XGBoost模型 → {xgb_path}")

    # ========== 对比总结 ==========
    print("\n" + "=" * 60)
    print("模型对比结果")
    print("=" * 60)
    print(f"{'指标':<10} {'LSTM':>12} {'XGBoost':>12} {'优胜':>8}")
    print("-" * 44)
    for metric in ["MAE", "RMSE", "MAPE"]:
        lstm_val = lstm_metrics[metric]
        xgb_val = xgb_metrics.get(metric, 0)
        winner = "LSTM" if lstm_val < xgb_val else "XGB"
        print(f"{metric:<10} {lstm_val:>12.3f} {xgb_val:>12.3f} {winner:>8}")

    return {
        "lstm": lstm_metrics,
        "xgboost": xgb_metrics,
        "history": history,
    }


if __name__ == "__main__":
    result = main()
