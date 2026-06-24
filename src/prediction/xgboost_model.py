"""
XGBoost客流预测基线模型

作为LSTM的对比基线，使用XGBoost回归模型进行客流预测。
XGBoost不需要序列数据，直接使用手工特征进行预测。
"""
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from typing import Union

from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))


class XGBoostPredictor:
    """XGBoost客流预测器"""

    def __init__(self, params: dict = None):
        """
        Args:
            params: XGBoost超参数，默认使用调优后的参数
        """
        self.params = params or {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 1.0,
            "reg_lambda": 1.0,
            "random_state": 42,
        }
        self.model = XGBRegressor(**self.params)
        self.feature_importance_ = None

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series,
            X_val: pd.DataFrame = None, y_val: pd.Series = None) -> None:
        """训练模型"""
        print("[XGBoost] 开始训练...")

        eval_set = [(X_train.values, y_train.values)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val.values, y_val.values))

        self.model.fit(
            X_train.values, y_train.values,
            eval_set=eval_set if len(eval_set) > 1 else None,
            verbose=False,
        )
        self.feature_importance_ = dict(
            zip(X_train.columns, self.model.feature_importances_)
        )

        print(f"[XGBoost] 训练完成")
        top_features = sorted(self.feature_importance_.items(),
                             key=lambda x: x[1], reverse=True)[:5]
        print("  Top-5 重要特征:")
        for name, imp in top_features:
            print(f"    {name}: {imp:.4f}")

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """预测"""
        if isinstance(X, pd.DataFrame):
            return self.model.predict(X.values)
        return self.model.predict(X)

    def evaluate(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
        """计算评估指标"""
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        mape = np.mean(np.abs(
            (y_true - y_pred) / np.clip(y_true, 1e-5, None)
        )) * 100

        metrics = {"MAE": round(mae, 3), "RMSE": round(rmse, 3), "MAPE": round(mape, 2)}
        return metrics

    def get_feature_importance(self) -> dict:
        """获取特征重要性"""
        return self.feature_importance_ or {}


if __name__ == "__main__":
    print("[XGBoost模型] 模块加载成功")
