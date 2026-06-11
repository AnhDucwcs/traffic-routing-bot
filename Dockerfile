# 1. Chọn Base Image
FROM python:3.11-slim

# 2. Thiết lập biến môi trường
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Tạo user với UID 1000 ngay từ đầu
RUN useradd -m -u 1000 user

# 4. Cài đặt các thư viện hệ thống (Chạy bằng quyền root)
# Gộp chung gcc, build-essential và libspatialindex-dev (cần cho OSMnx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Tạo thư mục làm việc và cấp luôn quyền cho user
WORKDIR /traffic_routing_bot
RUN chown user:user /traffic_routing_bot

# 6. Copy và cài đặt thư viện Python
# Cấp quyền user cho file requirements ngay khi copy vào
COPY --chown=user:user ./requirements.txt /traffic_routing_bot/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /traffic_routing_bot/requirements.txt

# 7. Copy toàn bộ mã nguồn (bao gồm file routing_brain.pkl) vào container
COPY --chown=user:user . /traffic_routing_bot

# 8. Chuyển xuống chạy bằng user vừa tạo (BẮT BUỘC cho Hugging Face Spaces)
USER user

# 9. Mở port
EXPOSE 7860

# 10. Lệnh khởi động Server FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]