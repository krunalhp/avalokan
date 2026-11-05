"""YOLOX Nano 416 ONNX contract; no training framework in the inference path.

Artifact/preprocessing contract: Megvii YOLOX demo/ONNXRuntime (Apache-2.0).
Decoding uses the published anchor-free grid/stride parameterization.
"""

import hashlib

import cv2
import numpy as np
import onnxruntime as ort

from .contracts import CLASSES
from .settings import MODEL_SHA256


class Detector:
    def __init__(self, path):
        if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("Model checksum mismatch; run the model installer")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self.session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.mgrid[: 416 // stride, : 416 // stride]
            grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
            strides.extend([stride] * x.size)
        self.grid = np.concatenate(grids)
        self.strides = np.array(strides)[:, None]
        cv2.setNumThreads(1)

    def detect(self, image, classes, threshold):
        height, width = image.shape[:2]
        ratio = min(416 / height, 416 / width)
        canvas = np.full((416, 416, 3), 114, dtype=np.uint8)
        resized = cv2.resize(image, (int(width * ratio), int(height * ratio)))
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        tensor = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
        raw = self.session.run(None, {self.input: tensor})[0][0]
        if raw.shape != (3549, 85) or not np.isfinite(raw).all():
            raise ValueError("Unexpected model output")
        centers = (raw[:, :2] + self.grid) * self.strides
        sizes = np.exp(np.clip(raw[:, 2:4], -20, 20)) * self.strides
        corners = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / ratio
        # Pick the best COCO class before filtering, rather than relabeling an
        # excluded object's second-best class as an enabled class.
        labels = raw[:, 5:].argmax(axis=1)
        scores = raw[:, 4] * raw[np.arange(len(raw)), labels + 5]
        results = []
        for label, name in CLASSES.items():
            if name not in classes:
                continue
            mask = (labels == label) & (scores >= threshold)
            boxes, values = corners[mask], scores[mask]
            xywh = boxes.copy()
            xywh[:, 2:] -= xywh[:, :2]
            keep = cv2.dnn.NMSBoxes(xywh.tolist(), values.tolist(), threshold, 0.45)
            for i in np.asarray(keep).reshape(-1):
                box = np.clip(boxes[i] / [width, height, width, height], 0, 1)
                if box[2] > box[0] and box[3] > box[1]:
                    results.append((name, float(values[i]), tuple(float(v) for v in box)))
        return sorted(results, key=lambda x: x[1], reverse=True)[:200]
