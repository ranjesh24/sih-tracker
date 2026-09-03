import cv2
import torch
import easyocr
import torchreid
from ultralytics import YOLO
from torchvision import transforms
from PIL import Image

print("Loading Models... This might take a few seconds.")

# 1. Load YOLO 
yolo_model = YOLO('yolov8s.pt')

# 2. Load OCR
ocr_reader = easyocr.Reader(['en'])

# 3. Load ReID 
reid_model = torchreid.models.build_model(
    name='osnet_x1_0', 
    num_classes=1000,
    loss='softmax',
    pretrained=True 
)
reid_model.eval()

reid_transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def get_embedding_from_crop(cropped_img):
    """Fuses OSNet structural features with a dense HSV Color Histogram."""
    # 1. Get Deep Structural Features (OSNet)
    img_rgb = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    img_tensor = reid_transform(pil_img).unsqueeze(0)
    with torch.no_grad():
        # Get shape [512] and normalize
        osnet_emb = reid_model(img_tensor).squeeze()
        osnet_emb = torch.nn.functional.normalize(osnet_emb, p=2, dim=0)

    # 2. Get Color Features (HSV Histogram)
    hsv_img = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2HSV)
    # 8 bins for Hue, Saturation, and Value = 512 length array
    hist = cv2.calcHist([hsv_img], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    
    hist_tensor = torch.tensor(hist.flatten(), dtype=torch.float32)
    hist_tensor = torch.nn.functional.normalize(hist_tensor, p=2, dim=0)

    # 3. Fuse and Re-normalize (50% Structure, 50% Color)
    combined_emb = torch.cat((osnet_emb, hist_tensor)).unsqueeze(0) # Shape: [1, 1024]
    combined_emb = torch.nn.functional.normalize(combined_emb, p=2, dim=1)
    
    return combined_emb

def process_frame(image_path):
    img = cv2.imread(image_path)
    results = yolo_model(img, conf=0.25, classes=[2, 3, 5, 7])[0]
    
    # ---------------------------------------------------------
    # FIX 1: FIND THE LARGEST BOUNDING BOX (The Main Car)
    # ---------------------------------------------------------
    largest_box = None
    max_area = 0
    
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        area = (x2 - x1) * (y2 - y1)
        if area > max_area:
            max_area = area
            largest_box = (x1, y1, x2, y2)
            
    if largest_box is None:
        return None
        
    x1, y1, x2, y2 = largest_box
    
    # Crop the main vehicle for Re-ID
    cropped_vehicle = img[y1:y2, x1:x2]
    embedding = get_embedding_from_crop(cropped_vehicle)
    
    # ---------------------------------------------------------
    # FIX 2: CROP ONLY THE BOTTOM 40% OF THE CAR FOR OCR
    # ---------------------------------------------------------
    h = y2 - y1
    plate_y_start = int(y1 + (h * 0.60)) # Start 60% of the way down
    bottom_crop = img[plate_y_start:y2, x1:x2]
    
    ocr_result = ocr_reader.readtext(bottom_crop)
    
    # Get the longest text string found in the bottom crop (most likely the plate)
    plate_text = "No Plate Detected"
    if ocr_result:
        longest_text = ""
        for bbox, text, conf in ocr_result:
            if len(text) > len(longest_text):
                longest_text = text
        plate_text = longest_text

    return {
        "box": largest_box,
        "plate": plate_text,
        "embedding": embedding
    }
def analyze_vehicle(image_path):
    result = process_frame(image_path)
    if result is None:
        return {"error": "No vehicle detected"}
    return {
        "plate": result["plate"],
        "bounding_box": result["box"],
        "embedding": result["embedding"].tolist()
    }

# ==========================================
# EXECUTE AND TEST ALL 4 IMAGES
# ==========================================
print("\nProcessing images...")
data_a1 = process_frame("sample_data/reid_test/car_a_cam1.jpeg")
data_a2 = process_frame("sample_data/reid_test/car_a_cam2.jpeg")
data_a3 = process_frame("sample_data/reid_test/car_a_cam3.jpeg")
data_b1 = process_frame("sample_data/reid_test/car_b_cam1.jpeg")

print("\n=== OCR RESULTS (BOTTOM CROP) ===")
print(f"Car A (Cam 1) Plate: {data_a1['plate']}")
print(f"Car A (Cam 2) Plate: {data_a2['plate']}")
print(f"Car A (Cam 3) Plate: {data_a3['plate']}")
print(f"Car B (Cam 1) Plate: {data_b1['plate']}")

print("\n=== RE-ID SIMILARITY MATCHING ===")
# Helper to calculate similarity
def get_sim(emb1, emb2):
    return torch.nn.functional.cosine_similarity(emb1, emb2).item()

print("--- SAME CAR COMPARISONS (Expect HIGH) ---")
print(f"Car A Cam1 vs Car A Cam2: {get_sim(data_a1['embedding'], data_a2['embedding']):.4f}")
print(f"Car A Cam1 vs Car A Cam3: {get_sim(data_a1['embedding'], data_a3['embedding']):.4f}")
print(f"Car A Cam2 vs Car A Cam3: {get_sim(data_a2['embedding'], data_a3['embedding']):.4f}")

print("\n--- DIFFERENT CAR COMPARISON (Expect LOW) ---")
print(f"Car A Cam1 vs Car B Cam1: {get_sim(data_a1['embedding'], data_b1['embedding']):.4f}")