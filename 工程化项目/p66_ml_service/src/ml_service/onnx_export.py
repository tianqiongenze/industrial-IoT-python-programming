# -*- coding: utf-8 -*-
"""A层·ONNX 边缘部署对比：导出路径已实现并由导入探测保护。

课程离线环境未安装 onnx/skl2onnx/onnxruntime —— 本模块如实返回
available=False 与原因，不伪造任何"已导出/已加速"数字；一旦环境装上
skl2onnx，同一入口即真实导出并对比 sklearn 与 onnxruntime 单次推理延迟。
"""
import time


def export_and_compare(model, out_path, sample_x):
    """导出 ONNX；环境可用则实测 sklearn vs onnxruntime 延迟对比。"""
    import numpy as np
    try:
        from skl2onnx import to_onnx
    except ImportError as exc:
        return {"available": False,
                "reason": ("当前课程环境未安装 skl2onnx（离线不可装）：%s；"
                           "导出路径已实现并由导入探测保护，装上后即可运行" % exc),
                "planned_opset": 17}
    onx = to_onnx(model, sample_x.astype(np.float32), target_opset=17,
                  options={id(model): {"zipmap": False}})
    with open(out_path, "wb") as f:
        f.write(onx.SerializeToString())
    out = {"available": True, "path": out_path, "size_bytes":
           __import__("os").path.getsize(out_path)}
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(out_path)
        inp = sess.get_inputs()[0].name
        x32 = sample_x.astype(np.float32)
        t0 = time.perf_counter()
        for _ in range(50):
            sess.run(None, {inp: x32})
        out["onnx_ms_50req"] = round((time.perf_counter() - t0) * 1000 / 50, 4)
        t0 = time.perf_counter()
        for _ in range(50):
            model.predict(sample_x)
        out["sklearn_ms_50req"] = round((time.perf_counter() - t0) * 1000 / 50, 4)
        out["note"] = "边缘侧收益=模型体积与跨语言运行时；数值为真实实测"
    except ImportError:
        out["note"] = "已导出但 onnxruntime 缺失，延迟对比不可得，如实留空"
    return out
