## Yêu cầu môi trường

- Python 3.9+
- pip

### Cài đặt thư viện

```bash
pip install ultralytics opencv-python pillow
```

Nếu chạy trên môi trường headless / server:

```bash
pip install ultralytics opencv-python-headless pillow
```
---


### 3) `image_folder_manager.py`

Script quản lý ảnh/folder bằng giao diện GUI Tkinter.

Chức năng:
- duyệt ảnh theo thư mục
- xem các subfolder
- xóa ảnh hoặc xóa cả folder
- di chuyển ảnh/folder sang thư mục khác
- đi trước/sau qua các folder theo thứ tự

Usage:

```bash
python image_folder_manager.py
```

Nếu không truyền đường dẫn, chương trình sẽ mở hộp thoại chọn thư mục.

---

## Tài liệu tham khảo nhanh

- YOLO: https://docs.ultralytics.com/
- OpenCV: https://opencv.org/
- BoT-SORT tracker: https://github.com/NirAharon/BoT-SORT

---

## Kết luận

Project này là một bộ công cụ xử lý dữ liệu Re-ID theo kiểu chuẩn hóa dataset → sẵn sàng cho training hoặc matching identity. Nếu làm đúng pipeline, dữ liệu sẽ dễ quản lý, dễ kiểm tra và dễ thống nhất giữa các camera.
