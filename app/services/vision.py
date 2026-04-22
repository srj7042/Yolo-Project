import os
import cv2
import torch
import numpy as np
from PIL import Image
from ultralytics import YOLO
from facenet_pytorch import MTCNN, InceptionResnetV1
from app.models import Student
from flask import current_app

# Load MTCNN for deep face cropping, Resnet for encoding
# Force CPU because MTCNN has a known bug with PyTorch MPS backend (Adaptive pool MPS error)
device = torch.device('cpu')

mtcnn = MTCNN(keep_all=False, device=device) # detects single most prominent face for training
mtcnn_multi = MTCNN(keep_all=True, device=device) # detects multiple faces for classroom image if YOLO passes large crops
resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

# Load YOLOv8 for primary detection
yolo_model = YOLO('yolov8n.pt') 

def extract_face_tensor(img):
    """
    Attempt to extract face tensor using MTCNN directly.
    If it fails, use YOLO to find a person, crop the person, and try MTCNN again.
    """
    face_tensor = mtcnn(img)
    if face_tensor is not None:
        return face_tensor
        
    # Fallback to YOLO person detection
    results = yolo_model(img, classes=[0]) # class 0 is 'person'
    for r in results:
        boxes = r.boxes
        for box in boxes:
            # Crop the "person" using PIL
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            person_crop = img.crop((x1, y1, x2, y2))
            
            # Now extract the face tensor specifically from the person crop
            face_tensor = mtcnn(person_crop)
            if face_tensor is not None:
                return face_tensor
                
    return None

def generate_face_encoding(image_file):
    """
    Called when Admin uploads a student training photo.
    Extracts the face and returns the 512D embedding vector.
    """
    img = Image.open(image_file).convert('RGB')
    
    # Extract face
    face_tensor = extract_face_tensor(img)
    if face_tensor is None:
        return None
        
    # Get embedding
    face_tensor = face_tensor.unsqueeze(0).to(device) # shape: (1, 3, 160, 160)
    with torch.no_grad():
        embedding = resnet(face_tensor).cpu().numpy().flatten()
    
    return embedding

def generate_average_encoding(folder_path):
    """
    Loops through a folder of images for a single student, generates embeddings,
    and returns the average. This provides much more reliable recognition.
    """
    embeddings = []
    
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            file_path = os.path.join(folder_path, filename)
            
            try:
                img = Image.open(file_path).convert('RGB')
                face_tensor = extract_face_tensor(img)
                
                if face_tensor is not None:
                    face_tensor = face_tensor.unsqueeze(0).to(device)
                    with torch.no_grad():
                        emb = resnet(face_tensor).cpu().numpy().flatten()
                        embeddings.append(emb)
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                
    if not embeddings:
        return None
        
    # Average across all embeddings
    avg = np.mean(embeddings, axis=0)
    return avg

def process_classroom_image(image_path):
    """
    Called when Teacher uploads a classroom image.
    Uses YOLOv8 to find persons, crops them, then encodes the face inside the crop
    to match against the database to mark attendance. Returns a list of matched student IDs.
    """
    img = Image.open(image_path).convert('RGB')
    results = yolo_model(img, classes=[0]) # class 0 is 'person' in COCO dataset
    
    matched_student_ids = []
    
    # Load all known students from DB
    with current_app.app_context():
        students = Student.query.filter(Student.face_encoding.isnot(None)).all()
        known_encodings = [s.get_encoding() for s in students]
        known_ids = [s.id for s in students]
        
        if not known_encodings:
            return [] # No students in database with face data
    
    # Process YOLO bounding boxes
    for r in results:
        boxes = r.boxes
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            
            # Crop the "person" using PIL
            person_crop = img.crop((x1, y1, x2, y2))
            
            # Now extract the face tensor specifically from the person crop
            face_tensor = mtcnn(person_crop)
            if face_tensor is not None:
                face_tensor = face_tensor.unsqueeze(0).to(device)
                with torch.no_grad():
                    unknown_encoding = resnet(face_tensor).cpu().numpy().flatten()
                
                # Compare against all known
                best_match_id = None
                min_dist = float('inf')
                
                for idx, known_enc in enumerate(known_encodings):
                    # Calculate Euclidean distance between embedding vectors
                    dist = np.linalg.norm(known_enc - unknown_encoding)
                    if dist < min_dist:
                        min_dist = dist
                        best_match_id = known_ids[idx]
                
                # Threshold for Facenet Face Match (Typically < 0.8 is a match for vggface2)
                if min_dist < 0.8:
                    if best_match_id not in matched_student_ids:
                        matched_student_ids.append(best_match_id)
                        
    return matched_student_ids
