---
{"id": "ai_ml:case:defect-vision", "project": "defect-vision", "title": "Real-time defect detection on an assembly line", "client_industry": "manufacturing", "category": "computer_vision", "date": "2021-11-10", "skills": ["YOLO", "PyTorch", "OpenCV", "ONNX", "edge deployment"]}
---
# Real-time defect detection on an assembly line

## The problem
Manual inspection missed hairline cracks on cast parts at 2 parts per second.

## What I did
Trained a YOLOv8 detector on augmented crack images and exported it to ONNX for a Jetson edge box.

## Result
Recall 96% at 38 FPS; scrap reaching customers fell by half.

## Stack
YOLO, PyTorch, OpenCV, ONNX, edge deployment
