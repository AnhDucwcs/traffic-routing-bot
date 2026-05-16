# 1. Chọn Base Image: Dùng bản slim để dung lượng nhẹ, khởi động nhanh
FROM python:3.11-slim

# 2. Thiết lập biến môi trường
# Ngăn Python tạo ra các file .pyc dư thừa và ép in log trực tiếp ra terminal
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Tạo thư mục làm việc trong container
WORKDIR /traffic_routing_bot

# (Tùy chọn) Cài đặt các thư viện lõi của Linux hệ điều hành nếu OSMnx/Geopandas yêu cầu
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libspatialindex-dev && rm -rf /var/lib/apt/lists/*

# 4. Copy và cài đặt thư viện (Tận dụng Docker Cache)
COPY ./requirements.txt /traffic_routing_bot/requirements.txt
RUN apt-get update && apt-get install -y gcc build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade -r /traffic_routing_bot/requirements.txt
# 5. Thiết lập User cho Hugging Face (BẮT BUỘC)
# Hugging Face yêu cầu ứng dụng phải chạy dưới một user thông thường (UID 1000), không được dùng quyền root.
RUN useradd -m -u 1000 user
USER user

# 6. Copy toàn bộ mã nguồn (bao gồm file routing_brain.pkl) vào container
COPY --chown=user . /traffic_routing_bot

# 7. Mở port (Hugging Face Spaces mặc định giao tiếp qua port 7860)
EXPOSE 7860

# 8. Lệnh khởi động Server FastAPI
# Giả sử file chứa app FastAPI của bạn tên là main.py và biến khởi tạo là app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]