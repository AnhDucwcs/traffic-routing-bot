## 1. Kiến trúc Lưu trữ Kép (Dual-Database Architecture)

Dự án áp dụng mô hình kiến trúc lưu trữ tách biệt để giải quyết hai bài toán có tính chất trái ngược nhau:

- **Hot Storage (Kho Nóng):** Cung cấp dữ liệu Tức thời (Real-time) với độ trễ cực thấp cho Thuật toán A* tìm đường.
- **Cold Storage (Kho Lạnh):** Lưu trữ vĩnh viễn dữ liệu Thô & Lịch sử (Historical Data) phục vụ cho việc huấn luyện mô hình Machine Learning/AI trong tương lai mà không làm tốn chi phí bộ nhớ.

## 2. Kho Nóng (Hot Storage) - MongoDB

- **Mục đích:** Phục vụ trực tiếp cho tính năng tìm đường của Telegram Bot.
- **Đặc tính:** Siêu gọn nhẹ, I/O cực cao, và tự động dọn rác (Ephemeral).
- **Database:** `traffic_db`
- **Collection:** `bus_speeds`

### 2.1. Cấu trúc Document (Schema)

Dữ liệu đã được hệ thống Crawler sàng lọc (Sanitized), loại bỏ hoàn toàn các "Ảo giác GPS" (ví dụ xe chạy > 80km/h) và nhiễu do xe dừng trạm đón khách (<60m), các giá trị vận tốc < 5km/h đều sẽ được đổi lại thành 5km/h để tránh ảnh hưởng đến việc tính trọng số phạt.

JSON

```
{
  "from_stop_id": "417",                                 // ID Trạm bắt đầu của đoạn đường (Node U)
  "to_stop_id": "418",                                   // ID Trạm kết thúc của đoạn đường (Node V)
  "instant_speed_kmh": 6.38,                             // Vận tốc lấy từ api
  "timestamp": {"$date": "2026-06-14T07:45:52.589Z"}     // Thời điểm bản ghi được lưu
}
```

### 2.2. Chiến lược Chỉ mục (Indexing Strategy)

Để đảm bảo MongoDB duy trì dung lượng ở mức siêu thấp (dưới 512MB) và tốc độ đọc/ghi tối đa:

1. **Compound Unique Index:** Đánh chỉ mục trên cặp `[from_stop_id, to_stop_id]`. Crawler sẽ dùng lệnh `UPSERT` dựa trên cặp khóa này để liên tục **ghi đè** vận tốc mới nhất lên đoạn đường, không tạo ra bản ghi thừa.
2. **TTL Index (Time-To-Live):** Đánh chỉ mục tự hủy trên trường `timestamp` với giới hạn **3600 giây (60 phút)**. Bất kỳ đoạn đường nào không có xe buýt chạy qua cập nhật trong 60 phút sẽ bị xóa, thuật toán A* sẽ tự động Fallback về trọng số thời gian tĩnh mặc định.

## 3. Kho Lạnh (Cold Storage) - Data Lake

- **Nền tảng:** Hugging Face Datasets (hoặc Google Cloud Storage).
- **Mục đích:** Hồ dữ liệu (Data Lake) lưu trữ ngữ cảnh thô (Contextual Raw Data) phục vụ cho Phân tích Dữ liệu (EDA) và Huấn luyện AI dự đoán kẹt xe (Predictive Routing) trong tương lai.
- **Đặc tính:** Lưu mọi thứ (kể cả dữ liệu lỗi, nhiễu), vĩnh viễn không bao giờ xóa (Zero-deletion policy).
- **Định dạng:** Lưu dạng cột (Columnar format) bằng file `.parquet` giúp nén dung lượng siêu nhỏ và tối ưu tốc độ đọc trực tiếp vào RAM cho thư viện Pandas/Polars.

### 3.1. Cấu trúc Dữ liệu (Schema)

Lưu trữ toàn cảnh trạng thái vật lý của chiếc xe buýt tại một thời điểm cắt ngang (Snapshot), không vứt bỏ các dữ liệu ngoại lệ (Outliers) để AI tự học cách phân biệt.

JSON

```
{
  "timestamp": "2026-05-29T14:30:00Z",                                 // Thời gian hệ thống cào dữ liệu (Mốc tuyệt đối)
  "route_id": "55",                                                    // Mã tuyến xe buýt
  "var_id": str(var_id),                                               // Mã chiều hiện tại của tuyến
  "vehicle_id": "50E22080",                                            // Biển số định danh xe
  "to_current_stop_id": "417",                                         // ID Trạm hiện tại
  "to_next_stop_id": "418",                                            // ID Trạm tiếp theo
  "distance_to_current_stop": round(distance_to_current_stop, 2),      // Khoảng cách còn lại tới trạm hiện tại (mét)
  "time_to_current_stop": round(time_to_current_stop, 2),              // Thời gian dự kiến tới trạm hiện tại (giây)
  "distance_to_next_stop": 4765.84,                                    // Khoảng cách còn lại tới trạm tiếp theo (mét)
  "time_to_next_stop": round(time_to_next_stop, 2),                    // Thời gian dự kiến tới trạm tiếp theo (giây)
  "instant_speed_kmh": 23.0,                                           // Vận tốc tức thời từ GPS (Sẽ là 0.0 khi xe dừng trạm/đèn đỏ)
}
```

### 3.2. Chiến lược Lưu trữ & Phân mảnh (Partitioning Strategy)

Áp dụng chiến trúc gom lô (Micro-batching) thay vì ghi lắt nhắt từng dòng để tránh quá tải API của Cloud Storage và bảo toàn dữ liệu khi server restart:

1. **Buffer (Ghi tạm):** Trong quá trình Crawler chạy, dữ liệu thô liên tục được `append` (ghi nối tiếp) vào một file tạm ở ổ cứng của server (VD: `/tmp/raw_data.jsonl`).
2. **Batching (Đóng gói):** Cứ định kỳ **1 giờ/lần**, một luồng Background Task sẽ đọc file tạm này, chuyển đổi (cast) sang định dạng PyArrow và nén thành một file `.parquet` duy nhất.
3. **Partitioning (Phân mảnh theo Hive-style):** File Parquet được bắn lên Hugging Face Datasets và tổ chức theo cấu trúc cây thư mục thời gian chuẩn MLOps để AI dễ dàng trích xuất sau này:
    `/data/traffic_{year=2026}-{month=06}.parquet`
4. **Cleanup (Dọn dẹp):** Chỉ khi nhận được HTTP Status 200 (Upload thành công) từ Cloud, hệ thống mới tự động xóa file tạm `/tmp/raw_data.jsonl` để bắt đầu chu kỳ 1 giờ tiếp theo.
