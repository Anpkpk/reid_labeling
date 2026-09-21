"""
Tách từng người (full-body) ra folder riêng cho TẤT CẢ video trong 1 folder
(ví dụ folder "Cam 1" chứa nhiều file .mp4 quay cùng 1 camera ở các thời điểm
khác nhau). Mỗi người lấy ảnh cách nhau khoảng N giây (mặc định 1s).

Cài đặt thư viện cần thiết (chạy 1 lần):
    pip install ultralytics opencv-python

Cách chạy:
    python extract_people.py --video_dir "data/Cam 1-20260505T112914Z-3-001/Cam 1" --out output --interval 1.0

Giải thích cách hoạt động:
  - Quét tất cả file video (.mp4, .mov, .avi, .mkv) trong --video_dir.
  - Với MỖI video, chạy YOLOv8 + tracker (ByteTrack/BoT-SORT) riêng biệt để
    theo dõi từng người xuyên suốt video đó và gán track_id.
  - LƯU Ý QUAN TRỌNG: track_id KHÔNG liên tục giữa các video khác nhau (mỗi
    video tracker chạy lại từ đầu), nên kết quả được tách theo từng video:
        out/<ten_video_1>/person_1/, person_2/, ...
        out/<ten_video_2>/person_1/, person_2/, ...
    Nếu muốn gộp đúng người xuất hiện ở nhiều video/clip khác nhau của cùng
    1 cam, dùng tiếp script merge_identities.py để so khớp ngoại hình giữa
    các folder này (tương tự cách gộp giữa nhiều camera).
"""

import argparse
import os
from collections import defaultdict
from glob import glob

import cv2
from ultralytics import YOLO

VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")


def find_videos(video_dir):
    files = []
    for ext in VIDEO_EXTENSIONS:
        files.extend(glob(os.path.join(video_dir, f"*{ext}")))
        files.extend(glob(os.path.join(video_dir, f"*{ext.upper()}")))
    return sorted(set(files))


def process_video(video_path, out_root, model, args):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(out_root, video_name)
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  [BỎ QUA] Không mở được video: {video_path}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.release()

    frame_interval = max(1, round(fps * args.interval))
    print(f"\n=== Xử lý: {video_path} ===")
    print(f"FPS: {fps:.2f} | Cứ mỗi {frame_interval} frame ({args.interval}s) sẽ xét lưu ảnh")

    last_saved_frame = defaultdict(lambda: -10**9)
    saved_count = defaultdict(int)
    frame_idx = 0

    results_generator = model.track(
        source=video_path,
        classes=[0],          # class 0 = "person" trong COCO dataset
        conf=args.conf,
        tracker=args.tracker,
        stream=True,
        persist=True,
        verbose=False,
    )

    for result in results_generator:
        frame = result.orig_img
        h, w = frame.shape[:2]

        if result.boxes is not None and result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            ids = result.boxes.id.cpu().numpy().astype(int)

            for box, pid in zip(boxes, ids):
                x1, y1, x2, y2 = box
                bw, bh = x2 - x1, y2 - y1

                if (bw * bh) / (w * h) < args.min_box_area_ratio:
                    continue

                # Bỏ qua box "không đủ toàn thân" (vd: chỉ thấy đầu/vai khi người
                # đứng quá gần camera nên phần dưới bị cắt khỏi khung hình)
                aspect_ratio = bh / bw if bw > 0 else 0
                if aspect_ratio < args.min_aspect_ratio:
                    continue

                # Bỏ qua box bị cắt sát mép trên hoặc mép dưới khung hình
                # (dấu hiệu cơ thể bị cắt mất, không lấy được toàn thân)
                edge_margin = 2  # pixel
                if y1 <= edge_margin or y2 >= h - edge_margin:
                    continue

                if frame_idx - last_saved_frame[pid] < frame_interval:
                    continue

                x1 = max(0, x1 - bw * args.padding)
                y1 = max(0, y1 - bh * args.padding)
                x2 = min(w, x2 + bw * args.padding)
                y2 = min(h, y2 + bh * args.padding)

                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                person_dir = os.path.join(out_dir, f"person_{pid}")
                os.makedirs(person_dir, exist_ok=True)

                saved_count[pid] += 1
                out_path = os.path.join(
                    person_dir, f"frame_{saved_count[pid]:04d}_t{frame_idx / fps:.1f}s.jpg"
                )
                cv2.imwrite(out_path, crop)

                last_saved_frame[pid] = frame_idx

        frame_idx += 1

    print(f"Xong video {video_name}. Kết quả:")
    for pid, count in sorted(saved_count.items()):
        print(f"  person_{pid}: {count} ảnh -> {os.path.join(out_dir, f'person_{pid}')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_dir", default="data/",
                         help="Folder chứa nhiều video cần xử lý (ví dụ folder 'Cam 1')")
    parser.add_argument("--out", default="output", help="Folder output gốc")
    parser.add_argument("--interval", type=float, default=2.0,
                         help="Khoảng cách thời gian giữa các ảnh lưu, tính theo giây (mặc định 1s)")
    parser.add_argument("--model", default="yolo26s.pt",
                         help="Model YOLOv26 dùng để detect người. "
                              "yolo26n.pt = nhanh nhất nhưng kém chính xác, "
                              "yolo26m.pt = cân bằng (khuyên dùng), yolo26l.pt/yolo26x.pt = chính xác nhất nhưng chậm")
    parser.add_argument("--conf", type=float, default=0.5, help="Ngưỡng confidence để nhận diện người")
    parser.add_argument("--padding", type=float, default=0.0,
                         help="Tỉ lệ mở rộng thêm xung quanh bounding box khi crop (0.08 = thêm 8%)")
    parser.add_argument("--tracker", default="botsort_reid.yaml",
                         help="botsort_reid.yaml (có Re-ID, giữ đúng ID người tốt hơn khi bị che/mất khung hình) "
                              "hoặc bytetrack.yaml (nhanh hơn nhưng dễ nhảy ID)")
    parser.add_argument("--min-box-area-ratio", type=float, default=0.0015,
                         help="Bỏ qua các box quá nhỏ so với khung hình (người ở quá xa / nhiễu), "
                              "tỉ lệ so với diện tích khung hình")
    parser.add_argument("--min-aspect-ratio", type=float, default=1.4,
                         help="Tỉ lệ tối thiểu height/width của box để coi là 'đủ toàn thân'. "
                              "Người đứng full-body thường có tỉ lệ ~1.6-3.0 (cao hơn nhiều so với rộng). "
                              "Ảnh cận đầu/vai thường có tỉ lệ <1.3 (gần vuông hoặc rộng). "
                              "Tăng giá trị này lên (vd 1.8-2.0) nếu vẫn còn lọt ảnh cận mặt.")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    videos = find_videos(args.video_dir)
    if not videos:
        print(f"Không tìm thấy video nào trong folder: {args.video_dir}")
        return

    print(f"Tìm thấy {len(videos)} video trong '{args.video_dir}':")
    for v in videos:
        print(f"  - {v}")

    model = YOLO(args.model)  # tự động tải model lần đầu chạy nếu chưa có

    for video_path in videos:
        process_video(video_path, args.out, model, args)

    print("\n=== HOÀN TẤT TOÀN BỘ ===")


if __name__ == "__main__":
    main()