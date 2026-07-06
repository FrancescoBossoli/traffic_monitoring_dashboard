from ultralytics import YOLO
import os
import glob


def fix_dataset_for_coco(dataset_dir):
    """
    Allinea il dataset Roboflow alle classi COCO del modello pre-addestrato
    """
    yaml_path = os.path.join(dataset_dir, "data.yaml")
    labels_dir = os.path.join(dataset_dir, "valid", "labels")

    # Riscrittura del data.yaml inserendo tutte le 80 classi COCO
    # per compatibilità con i pesi
    coco_yaml = f"""
        path: {os.path.abspath(dataset_dir)}
        train: train/images
        val: valid/images

        nc: 80
        names: [
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus',
            'train', 'truck', 'boat', 'traffic light', 'fire hydrant',
            'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog',
            'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe',
            'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
            'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat',
            'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
            'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl',
            'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
            'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
            'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop',
            'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven',
            'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase',
            'scissors', 'teddy bear', 'hair drier', 'toothbrush'
        ]
        """
    with open(yaml_path, "w") as f:
        f.write(coco_yaml.strip())

    # Correzione delle annotazioni txt:
    # Conversione di '0' (vehicle di Roboflow) in '2' (car di COCO)
    if os.path.exists(labels_dir):
        txt_files = glob.glob(os.path.join(labels_dir, "*.txt"))
        for file_path in txt_files:
            with open(file_path, "r") as f:
                lines = f.readlines()

            with open(file_path, "w") as f:
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) > 0 and parts[0] == '0':
                        parts[0] = '2'
                    f.write(" ".join(parts) + "\n")


if __name__ == '__main__':
    dataset_dir = os.path.abspath("roboflow_dataset")
    dataset_yaml_path = os.path.join(dataset_dir, "data.yaml")

    print(
        "Allineamento delle etichette Roboflow al modello YOLO pre-addestrato"
    )
    fix_dataset_for_coco(dataset_dir)

    model = YOLO("backend/weights/yolov8s.pt")

    print(f"\nInizio valutazione sul dataset: {dataset_yaml_path}")

    # Avvia della validazione limitandola alla classe 2 (Auto/Car)
    # workers=0 evita crash su Windows dovuti al multiprocessing
    metrics = model.val(
        data=dataset_yaml_path, split='val', workers=0, classes=[2]
    )

    print("\n--- RISULTATI DELLA VALUTAZIONE ---")
    print(f"mAP@50 (Precisione Media al 50% di IoU): {metrics.box.map50:.4f}")
    print(f"mAP@50-95 (Precisione Media rigorosa): {metrics.box.map:.4f}")
