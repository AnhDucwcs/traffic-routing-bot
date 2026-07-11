---
name: pytest-test-design
description: Standard guidelines for designing and structuring test files using the pytest framework.
---

# Quy định thiết kế Test (Pytest Standard)

Bất cứ khi nào Agent được yêu cầu tạo file test hoặc viết test, Agent BẮT BUỘC phải tuân thủ các quy định sau:

1. **Sử dụng Pytest:** Mọi file test phải được thiết kế để tương thích 100% với trình chạy `pytest` (không thiết kế dưới dạng script độc lập chạy bằng lệnh `python file.py`).
2. **Quy tắc Đặt tên:**
   - Tên file test phải bắt đầu bằng tiền tố `test_` (ví dụ: `test_map_matching.py`).
   - Tên hàm/phương thức test phải bắt đầu bằng tiền tố `test_` (ví dụ: `async def test_alley_snap():`).
3. **Môi trường Bất đồng bộ (Async):** Nếu hàm test có chứa từ khóa `async`, bắt buộc phải khai báo decorator `@pytest.mark.asyncio` ngay phía trên hàm.
4. **Setup & Teardown (Fixture):** Tận dụng tối đa sức mạnh của `pytest.fixture` (và `pytest_asyncio` nếu cần) để nạp dữ liệu nặng (như Load bản đồ, nạp TrafficManager) một lần duy nhất, tránh việc Load lại dữ liệu lặp đi lặp lại ở từng hàm test.
5. **Tính Độc Lập:** Các hàm test phải độc lập hoàn toàn với nhau, đảm bảo khi chạy riêng lẻ một hàm test bằng lệnh `pytest -k "tên_hàm"` thì nó vẫn chạy đúng.
