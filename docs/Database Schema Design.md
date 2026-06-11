## 1.  Hot Storage (MongoDB Atlas)
Lưu trữ vận tốc tức thời cào từ API xe buýt.

**Document Sample:**
```json
{
  "timestamp": { "$date": "2026-05-09T06:31:36.429Z" },
  "from_stop_id": "311",
  "next_stop_id": "312",
  "speed_ms": 4.89,
  "distance_to_next_stop": 150, 
  "_id": { "$oid": "69fed5d7b9fcfe42573917f9" }
}
````

- **TTL Index:** 86400 giây (24 giờ). Dữ liệu tự hủy sau 1 ngày.
- **Reference:** `next_stop_id` dùng để map với tọa độ trong `master_stops.json`.
- **Reference:** `distance_to_next_stop` để bổ sung thông tin về không gian. Khoảng cách còn lại đến trạm (mét). Dùng để xác định vị trí xe bắt đầu đi chậm trên cạnh (edge) của đồ thị.

## 2.  Cold Storage (Local Parquet)

Lưu trữ lịch sử giao thông đã qua xử lý và tổng hợp. Dữ liệu này được nén siêu cấp bằng định dạng Apache Parquet để phục vụ huấn luyện mô hình dự đoán.

**Cấu trúc bảng dữ liệu (Schema Table):**

|**Tên cột**|**Kiểu dữ liệu**|**Mô tả**|
|---|---|---|
|**`stop_id`**|`String`|ID của trạm xe buýt.|
|**`avg_speed`**|`Float`|Vận tốc trung bình trong khung giờ (m/s).|
|**`p50_distance`**|`Float`|Khoảng cách trung vị (Median) khi xe báo vận tốc này.|
|**`hour`**|`Int`|Khung giờ trong ngày (0-23).|
|**`day_of_week`**|`Int`|Thứ trong tuần (0: Thứ 2 ... 6: Chủ Nhật).|
|**`date`**|`String`|Ngày ghi nhận (YYYY-MM-DD).|
|**`congestion_level`**|`Int`|**Nhãn mức độ kẹt xe (0: Thoáng, 1: Chậm, 2: Đông, 3: Kẹt).**|

---

## Cơ chế gán nhãn tự động (Auto-Labeling Logic)

Trường `congestion_level` trong Cold Storage sẽ được hệ thống "Janitor" tự động tính toán vào cuối ngày dựa trên quy tắc sau:

1. **Lấy mốc chuẩn**: Tìm vận tốc cao nhất ($V_{max}$) của trạm đó vào khung giờ vắng vẻ (2h - 4h sáng).
2. **So sánh tỷ lệ ($R = V_{curr} / V_{max}$)**:
    - **Level 0 ($R > 0.8$)**: Thông thoáng (Xanh).
    - **Level 1 ($0.5 < R \le 0.8$)**: Di chuyển chậm (Vàng).
    - **Level 2 ($0.2 < R \le 0.5$)**: Ùn ứ cục bộ (Cam).
    - **Level 3 ($R \le 0.2$)**: Kẹt cứng (Đỏ).

> **Lưu ý đặc biệt**: Nếu `dist_to_stop` < 10m và vận tốc thấp, hệ thống sẽ tự động hạ mức kẹt xe về 0 để tránh nhầm lẫn với việc xe đang dừng trả khách.

**Lợi ích cho AI:**

Cung cấp tập dữ liệu sạch để huấn luyện mô hình dự đoán vận tốc theo thời gian (Time-series Forecasting). Giúp thuật toán A* không chỉ né kẹt xe hiện tại mà còn né được kẹt xe sắp xảy ra.