import torch
import torchreid
from torchvision import transforms
from PIL import Image

# Load the pretrained OSNet model (trained on VeRi-776)
model = torchreid.models.build_model(
    name='osnet_x1_0',
    num_classes=1000,  # placeholder, doesn't matter for feature extraction
    pretrained=True
)
model.eval()

# Standard preprocessing for OSNet input
transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                          std=[0.229, 0.224, 0.225])
])

def get_embedding(image_path):
    img = Image.open(image_path).convert('RGB')
    img = transform(img).unsqueeze(0)  # add batch dimension
    with torch.no_grad():
        embedding = model(img)
    return embedding

def cosine_similarity(a, b):
    return torch.nn.functional.cosine_similarity(a, b).item()

# Load your 4 images
paths = {
    "car_a_cam1": "sample_data/reid_test/car_a_cam1.jpg",
    "car_a_cam2": "sample_data/reid_test/car_a_cam2.jpg",
    "car_a_cam3": "sample_data/reid_test/car_a_cam3.jpg",
    "car_b_cam1": "sample_data/reid_test/car_b_cam1.jpg",
}

embeddings = {name: get_embedding(path) for name, path in paths.items()}

# Compare: same car (should be HIGH similarity)
print("=== SAME CAR comparisons (expect HIGH score) ===")
print("car_a_cam1 vs car_a_cam2:", cosine_similarity(embeddings["car_a_cam1"], embeddings["car_a_cam2"]))
print("car_a_cam1 vs car_a_cam3:", cosine_similarity(embeddings["car_a_cam1"], embeddings["car_a_cam3"]))
print("car_a_cam2 vs car_a_cam3:", cosine_similarity(embeddings["car_a_cam2"], embeddings["car_a_cam3"]))

# Compare: different car (should be LOW similarity)
print("\n=== DIFFERENT CAR comparison (expect LOW score) ===")
print("car_a_cam1 vs car_b_cam1:", cosine_similarity(embeddings["car_a_cam1"], embeddings["car_b_cam1"]))