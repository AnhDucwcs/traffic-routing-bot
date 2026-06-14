## 1. API lấy  danh sách trạm theo khu vực
- URL: https://apicms.ebms.vn/businfo/getstopsinbounds/{min_lng}/{min_lat}/{max_lng}/{max_lat}
- Mục đích: Lấy toàn bộ danh sách các trạm xe buýt trong phạm vi cụ thể.
- Chi tiết:
	- `min_lng` / `min_lat`: 106.58/10.70
	- `max_lng` / `max_lat`: 106.82/10.88
	- Data ban đầu có dạng:  ```
		`{
		  "iBus_Stops": {
		    "AddressNo": "135",
		    "Code": "Q1 137",
		    "Lat": 10.767064,
		    "Lng": 106.694824,
		    "Name": "KTX Trần Hưng Đạo",
		    "Routes": "01, 139, 152, 45, 53, 56, 75, 86, 88",
		    "Search": "KTHD 135 THD",
		    "Status": "Đang khai thác",
		    "StopId": 26,
		    "StopType": "Nhà chờ",
		    "Street": "Trần Hưng Đạo",
		    "SupportDisability": null,
		    "Ward": "Phường Cầu Ông Lãnh",
		    "Zone": "Quận 1"
		  }
		}`
	- Data lưu trong file có dạng:
		`{
			`"StopId": 26,
		    `"Name": "KTX Trần Hưng Đạo",
		    `"Lat": 10.767064,
		    `"Lng": 106.694824,
		    `"Routes": [01, 139, 152, 45, 53, 56, 75, 86, 88],
		`}

## 2. API dự báo các xe buýt đang đi tới trạm
- URL: https://apicms.ebms.vn/prediction/predictbystopid/{stop_id}
- Mục đích: Lấy tham số `v` để truyền vào api, lấy thông tin dự báo tại trạm hiện tại.
- Chi tiết: 
	- Các tham số:
		- stop_id: id của trạm cần dự báo
	- Data thu được:
		- URL ví dụ: https://apicms.ebms.vn/prediction/predictbystopid/26
	    {
	        "arrs": [
	            {
	                "d": 99.618775494990473,
	                "dts": "2026-05-28T16:58:51+07:00",
	                "s": 11.0,
	                "sts": 0,
	                "t": 19,
	                "v": "50F03035"
	            },
	            {
	                "d": 800.97976796666967,
	                "dts": "2026-05-28T16:58:33+07:00",
	                "s": 0.0,
	                "sts": 0,
	                "t": 154,
	                "v": "50H73998"
	            }
	        ],
	        "r": 128,
	        "rN": "Bến Thành - Chợ Long Phước",
	        "rNo": "88",
	        "s": 26,
	        "sN": "KTX Trần Hưng Đạo",
	        "v": 1,
	        "vN": "Chợ Long Phước"
	    }
	- Giải thích: 
		- arrs.d: khoảng cách còn lại tới trạm.
		- arrs.dts: Thời gian ghi nhận dự báo.
		- arrs.s: Vận tốc (km/h). Lưu ý: Đôi khi giá trị này có thể là 0.
		- arrs.sts: Có thể là Status.
		- arrs.t: Thời gian dự báo để xe đến trạm.
		- arrs.v: Biển số của xe buýt.
		- r: Mã định danh của tuyến xe.
		- rN: Tên của tuyến.
		- rNo: Số hiệu tuyến xe.
		- s: Mã của trạm.
		- sN: Tên trạm.
		- v: Có thể là mã lộ trình (chiều xe buýt đi).
		- vN: Tên của lộ trình đó.

## 3. API dự báo các xe buýt đang đi tới các trạm tiếp theo từ trạm gốc
- URL: https://apicms.ebms.vn/prediction/{route_id}/{v}/{stop_id}/predictnextstops/{limit}
- Mục đích: API này trả về các dự báo cho các trạm tiếp theo, từ đó lấy các thông tin cho database
- Chi tiết:
	- Các tham số:
		- route_id: Mã tuyến xe.
		- v: Mã lộ trình.
		- stop_id: Mã trạm gốc.
		- limit: Số lượng trạm cần dự báo.
	- Data thu được: 
		- URL ví dụ: https://apicms.ebms.vn/prediction/66/1/26/predictnextstops/1
		{
			"arrs": [
				{
					"d": 1915.9429605195535,
					"dts": "2026-05-29T11:44:25+07:00",
					"s": 15.0,
					"sts": 0,
					"t": 394,
					"v": "50E65864"
				},
				{
					"d": 4129.0381194038027,
					"dts": "2026-05-29T11:44:25+07:00",
					"s": 6.0,
					"sts": 0,
					"t": 852,
					"v": "50E65714"
				},
				{
					"d": 5403.1826530127073,
					"dts": "2026-05-29T11:44:25+07:00",
					"s": 0.0,
					"sts": 0,
					"t": 1127,
					"v": "50E65763"
				}
			],
			"r": 66,
			"rN": "Đại học Kinh tế - Bến Thành - Bến xe Miền Đông",
			"rNo": "45",
			"s": 27,
			"sN": "Nguyễn Kim",
			"v": 1,
			"vN": "Bến xe Miền Đông"
		}

## 4. Các API khác
- URL: https://apicms.ebms.vn/businfo/getallroute
- Mục đích: Lấy toàn bộ các tuyến xe buýt hiện tại

- URL: https://apicms.ebms.vn/businfo/getvarsbyroute/{route_id}
- Mục đích: Lấy các mã chiều của tuyến

- URL: https://apicms.ebms.vn/businfo/getpathsbyvar/{route_id}/{var_id} và https://apicms.ebms.vn/businfo/getstopsbyvar/{route_id}/{var_id}
- Mục đích: Lấy chuỗi các toạ độ và các id trạm của tuyến với chiều tương ứng.


