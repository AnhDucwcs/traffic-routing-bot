# **SYSTEM DESIGN DOCUMENT (SDD) \- SMARTCOMMUTE PLATFORM**

## **1: Kiến trúc Hệ thống (System Architecture)**

Mục đích của phần này là cung cấp bức tranh toàn cảnh (Bird's-eye view). Bất kỳ ai nhìn vào cũng biết dữ liệu đi từ điện thoại người dùng đến khi ra được bản đồ chỉ đường sẽ đi qua những trạm nào.

### **1.1. High-Level Design (Sơ đồ khối tổng thể):**

![][image1]

Mermaid syntax code: 

| \--- config:   theme: base   layout: dagre \--- flowchart TB  subgraph Client\_Layer\["Client Layer"\]         C\["Mobile App / Web UI"\]   end  subgraph Repo\_Messaging\["Repo: messaging-platform Java Spring Boot"\]         J\_Gateway\["WebSocket & REST Gateway"\]         J\_ChatLogic\["Chat & Routing Service"\]         DB\_PG\[("PostgreSQL\<br\>Users \&amp; Rooms")\]         DB\_MG\[("MongoDB\<br\>Messages")\]         DB\_RD\[("Redis Cache\<br\>Route \&amp; Session")\]   end  subgraph Repo\_AI\["Repo: traffic-routing-bot Python FastAPI"\]         P\_API\["FastAPI Endpoints"\]         P\_AI\["A\* Algorithm & OSMnx"\]         P\_Crawler\["Background Crawler Task"\]         DB\_Atlas\[("MongoDB Atlas M0\<br\>Hot Traffic Data")\]         DB\_Disk\[("HF Cold Storage\<br\>.feather / .parquet")\]   end  subgraph External\_Interfaces\["External Interfaces"\]         E\_BusAPI\["Buyttphcm API"\]   end     J\_Gateway \<-- "WSS / Real-time" \--\> J\_ChatLogic     J\_ChatLogic \-- CRUD \--\> DB\_PG & DB\_MG     J\_ChatLogic \<-- Check Cache / PubSub \--\> DB\_RD     P\_API \-- "asyncio.to\_thread" \--\> P\_AI     P\_AI \<-- Read RAM/Disk \--\> DB\_Disk     P\_AI \<-- Query TTL \--\> DB\_Atlas     P\_Crawler \-- Upsert Data \--\> DB\_Atlas     C \<-- "1. WSS Request/Response" \--\> J\_Gateway     J\_ChatLogic \-- "2. POST /routing (With Callback URL)" \--\> P\_API     P\_API \-. "3. 202 Accepted (Non-blocking)" .-\> J\_ChatLogic     P\_API \-- "4. POST {callbackUrl} (GeoJSON Result)" \--\> J\_ChatLogic     P\_Crawler \-- "5. HTTP GET (via VN Proxy)" \--\> E\_BusAPI      C:::client      J\_Gateway:::javaServer      J\_ChatLogic:::javaServer      DB\_PG:::database      DB\_MG:::database      DB\_RD:::database      P\_API:::pythonServer      P\_AI:::pythonServer      P\_Crawler:::pythonServer      DB\_Atlas:::database      DB\_Disk:::database      E\_BusAPI:::external     classDef client fill:\#f9f,stroke:\#333,stroke-width:2px     classDef javaServer fill:\#d4edda,stroke:\#28a745,stroke-width:2px     classDef pythonServer fill:\#cce5ff,stroke:\#0056b3,stroke-width:2px     classDef database fill:\#f8d7da,stroke:\#dc3545,stroke-width:2px     classDef external fill:\#fff3cd,stroke:\#ffc107,stroke-width:2px  |
| :---- |

### **1.2. Quyết định Công nghệ (Tech Stack & Justification):**

### **A. Phân hệ AI & Dữ liệu (Phần của bạn):**

Để đáp ứng yêu cầu tính toán lộ trình phức tạp và xử lý dữ liệu địa lý thời gian thực, phân hệ AI được xây dựng dựa trên các công nghệ sau:

* **Ngôn ngữ lập trình: Python 3.10+**

*Lý do:* Python cung cấp hệ sinh thái thư viện khoa học dữ liệu và xử lý đồ thị (Graph Processing) mạnh mẽ nhất hiện nay như NetworkX và OSMnx. Việc triển khai thuật toán A\* trên đồ thị hàng chục ngàn đỉnh trở nên hiệu quả và dễ bảo trì hơn so với các ngôn ngữ khác.

* **Web Framework: FastAPI**

*Lý do:* Tận dụng cơ chế async/await giúp server xử lý đồng thời nhiều yêu cầu cào dữ liệu và truy vấn API mà không bị nghẽn. FastAPI tự động sinh tài liệu chuẩn **OpenAPI (Swagger)**, giúp đối tác Java Spring Boot dễ dàng viết mã nguồn kết nối mà không cần tra cứu tài liệu thủ công.

* **Database: MongoDB Atlas (Cloud)**

*Lý do:* Dữ liệu vận tốc từ API xe buýt và các điểm kẹt xe có cấu trúc phi quan hệ (Unstructured), thường xuyên thay đổi. MongoDB cho phép mở rộng Schema linh hoạt. Đặc biệt, tính năng **TTL Index** (Time-To-Live) được thiết lập ở mức 60 phút sẽ tự động xóa dữ liệu cũ, đảm bảo bộ nhớ database luôn tinh gọn và chứa dữ liệu "tươi".

* **Thư viện xử lý lõi:**  
  * OSMnx: Tự động tải và chuẩn hóa bản đồ từ OpenStreetMap thành đồ thị toán học.  
  * Motor: Driver bất đồng bộ để giao tiếp với MongoDB mà không làm chặn Event Loop của FastAPI.	

  # **B. Phân hệ Messaging & Realtime Communication (Phần của đối tác)**

Để đáp ứng yêu cầu xử lý nhắn tin realtime, quản lý người dùng và đồng bộ dữ liệu tốc độ cao, phân hệ Messaging được xây dựng dựa trên các công nghệ sau:

## **Ngôn ngữ lập trình: Java 21**

Lý do:  
Java là ngôn ngữ ổn định và phổ biến trong phát triển hệ thống backend quy mô lớn. Java 21 cung cấp hiệu năng tốt, khả năng quản lý bộ nhớ ổn định và hỗ trợ mạnh cho các ứng dụng server-side nhiều kết nối đồng thời. Ngoài ra, hệ sinh thái Java rất phù hợp cho việc xây dựng kiến trúc backend rõ ràng, dễ maintain và mở rộng lâu dài.

## **Backend Framework: Spring Boot**

Lý do:  
Spring Boot giúp phát triển REST API và WebSocket nhanh chóng nhờ hệ sinh thái tích hợp sẵn như Spring Web, Spring Security và Spring Data.

Framework hỗ trợ:

* RESTful API  
* JWT Authentication  
* WebSocket Realtime  
* Database Integration  
* Dependency Injection  
* Structured Layered Architecture

Spring Boot giúp hệ thống dễ bảo trì, dễ mở rộng module và phù hợp với mô hình backend production thực tế.

## **Realtime Communication: Spring WebSocket \+ Redis Pub/Sub**

Lý do:  
Hệ thống sử dụng Spring WebSocket để xử lý giao tiếp realtime giữa client và server, cho phép gửi/nhận tin nhắn gần như tức thời.

Redis Pub/Sub được sử dụng nhằm:

* Đồng bộ sự kiện realtime  
* Quản lý trạng thái online/offline  
* Broadcast message giữa các kết nối WebSocket  
* Giảm tải xử lý trực tiếp trên database

Cơ chế này giúp hệ thống xử lý nhiều kết nối đồng thời với độ trễ thấp và tối ưu hiệu năng realtime messaging.

## **Relational Database: PostgreSQL**

Lý do:  
PostgreSQL được sử dụng để lưu trữ các dữ liệu quan hệ như:

* User  
* Authentication  
* Role/Permission  
* Friend relationship  
* Account metadata

PostgreSQL hỗ trợ ACID Transaction mạnh mẽ và đảm bảo tính toàn vẹn dữ liệu, phù hợp với các chức năng xác thực và quản lý tài khoản người dùng.

## **NoSQL Database: MongoDB**

Lý do:  
MongoDB được sử dụng để lưu:

* Chat messages  
* Conversation history  
* Realtime event logs

Tin nhắn là loại dữ liệu có số lượng lớn, thay đổi liên tục và không yêu cầu quan hệ phức tạp như relational database.

MongoDB giúp:

* Tăng tốc độ ghi dữ liệu  
* Linh hoạt thay đổi schema message  
* Dễ scale horizontal  
* Phù hợp với dữ liệu dạng document

Việc tách message sang MongoDB giúp giảm tải cho PostgreSQL và tối ưu hiệu năng hệ thống nhắn tin.

## **Cache & Session Storage: Redis**

Lý do:  
Redis hoạt động trên memory nên có tốc độ xử lý rất nhanh, phù hợp cho:

* Cache dữ liệu tạm thời  
* Session storage  
* Online user tracking  
* Token blacklist  
* WebSocket pub/sub  
* Rate limiting

Redis giúp giảm số lượng truy vấn trực tiếp đến database chính và cải thiện hiệu năng realtime của hệ thống.

## **Containerization: Docker**

Lý do:  
Toàn bộ hệ thống backend và database được đóng gói bằng Docker nhằm:

* Đồng nhất môi trường development và production  
* Dễ triển khai  
* Dễ scale service  
* Giảm lỗi cấu hình môi trường

Docker Compose được sử dụng để quản lý nhiều container như:

* Spring Boot  
* PostgreSQL  
* MongoDB  
* Redis

  ## **Reverse Proxy: Nginx**

Lý do:  
Nginx được sử dụng làm Reverse Proxy nhằm:

* Routing request  
* SSL/TLS termination  
* WebSocket proxy  
* Load balancing

Nginx giúp tăng tính ổn định và khả năng mở rộng của hệ thống trong môi trường production.

### **1.3. Cơ chế Xử lý Bất đồng bộ (Async/Concurrency Model):**

### **A. Phía AI Server:**

Đặc thù của Lõi AI là có sự kết hợp giữa tác vụ chờ đợi I/O (I/O-Bound) và tác vụ tính toán nặng (CPU-Bound). Chúng ta triển khai cơ chế **"Nhạc trưởng và Công nhân"**:

1. **Asyncio (Nhạc trưởng):**  
   * Đóng vai trò tiếp nhận yêu cầu từ Server Java, gọi API cào dữ liệu và ghi xuống MongoDB. Các tác vụ này tốn thời gian chờ mạng, nên dùng asyncio giúp server không lãng phí tài nguyên CPU trong lúc chờ đợi.  
2. **Worker Thread (Công nhân \- asyncio.to\_thread):**  
   * *Thách thức:* Thuật toán A\* tìm đường là tác vụ tiêu tốn 100% CPU. Nếu chạy trực tiếp trên luồng chính của FastAPI, nó sẽ làm "đóng băng" toàn bộ server, khiến Java không thể gọi API trong lúc AI đang tính.  
   * *Giải pháp:* Sử dụng asyncio.to\_thread() để đẩy toàn bộ logic tính toán A\* sang một luồng phụ (Worker Thread) độc lập.  
   * *Kết quả:* Server FastAPI vẫn phản hồi 202 Accepted cho đối tác Java ngay lập tức, trong khi luồng phụ vẫn âm thầm tính toán lộ trình ở dưới "nắp capo".

**B. Phía Chat Server :**

Đặc thù của Chat Server là phải duy trì số lượng lớn kết nối WebSocket realtime và xử lý đồng thời nhiều sự kiện như gửi tin nhắn, notification, trạng thái online/offline và phản hồi từ AI Routing Service mà không làm nghẽn hệ thống.

## **Spring WebFlux \+ Reactor Netty (Event Loop)**

Chat Server sử dụng:

* Spring WebFlux  
* Reactor Netty  
* Reactive Streams  
* Non-blocking I/O

để xây dựng cơ chế xử lý bất đồng bộ theo mô hình event-driven.

Thay vì tạo một thread riêng cho mỗi kết nối như blocking architecture truyền thống, Reactor Netty sử dụng Event Loop để quản lý hàng nghìn kết nối WebSocket đồng thời với số lượng thread nhỏ hơn nhiều.

Điều này giúp:

* Giảm tiêu thụ RAM và CPU  
* Tăng khả năng chịu tải realtime  
* Tránh hiện tượng thread exhaustion  
* Tối ưu hiệu năng khi có nhiều user online cùng lúc

## **Reactive Processing (Mono/Flux)**

Các request realtime như:

* send\_message  
* user\_typing  
* request\_route  
* notification

được xử lý bằng Reactive Stream thông qua:

* Mono  
* Flux

Nhờ đó server không bị chặn trong lúc:

* Chờ database phản hồi  
* Chờ Redis pub/sub  
* Chờ AI Routing Service xử lý

Hệ thống có thể tiếp tục phục vụ các user khác trong thời gian chờ.

## **Xử lý tác vụ nền bất đồng bộ**

Khi Client gửi yêu cầu tính tuyến đường:

1. Spring WebFlux nhận request từ WebSocket.  
2. Server gửi request bất đồng bộ sang AI Routing Service.  
3. Kết nối WebSocket của người dùng vẫn được giữ hoạt động.  
4. Các user khác vẫn gửi/nhận tin nhắn bình thường.  
5. Khi AI trả kết quả, Chat Server push realtime event receive\_route về đúng client.

Cơ chế này giúp tránh hiện tượng:

* Blocking thread  
* Server freeze  
* Delay toàn hệ thống khi AI xử lý lâu

## **Redis Pub/Sub cho Realtime Messaging**

Redis Pub/Sub được sử dụng để:

* Broadcast message  
* Đồng bộ sự kiện WebSocket  
* Tracking online user  
* Notification realtime

Khi có message mới:

1. Message được publish lên Redis Channel.  
2. Các WebSocket subscriber nhận sự kiện ngay lập tức.  
3. Tin nhắn được push realtime đến client tương ứng.

Cơ chế pub/sub giúp giảm tải xử lý trực tiếp trên Chat Server và hỗ trợ scale nhiều instance trong tương lai.

## **Kết quả đạt được**

Nhờ sử dụng:

* Spring WebFlux  
* Reactor Netty  
* Reactive Programming  
* Redis Pub/Sub

hệ thống có khả năng:

* Xử lý đồng thời hàng nghìn kết nối WebSocket  
* Duy trì realtime communication ổn định  
* Không bị "đóng băng" khi AI Routing Service xử lý lâu  
* Tăng khả năng mở rộng và chịu tải cho production environment

### **1.4. Hạ tầng triển khai (Hosting)**

Backend được triển khai bằng Docker Container nhằm đảm bảo tính nhất quán môi trường giữa development và production.

Hệ thống sử dụng:

* Spring Boot cho Backend API và WebSocket Server.  
* PostgreSQL lưu trữ dữ liệu quan hệ như người dùng, xác thực và quan hệ bạn bè.  
* MongoDB lưu trữ dữ liệu tin nhắn và lịch sử hội thoại.  
* Redis phục vụ caching, session và realtime event handling.

Các service được quản lý thông qua Docker Compose trong môi trường development và có thể mở rộng sang Kubernetes trong production.

Reverse Proxy sử dụng Nginx để:

* Routing request  
* SSL/TLS termination  
* Load balancing  
* WebSocket proxy

CI/CD có thể triển khai bằng GitHub Actions để tự động build, test và deploy hệ thống.

Hệ thống có thể được triển khai trên:

* VPS (Ubuntu Server)  
* AWS EC2  
* DigitalOcean  
* Google Cloud VM

* **Platform: Hugging Face Spaces (Dockerized)**  
  * Sử dụng Docker để đóng gói toàn bộ môi trường Python cùng các file đồ thị tĩnh (.pkl).  
  * Hạ tầng này cung cấp tài nguyên RAM lớn (tới 16GB) miễn phí, phù hợp để nạp bộ não đồ thị routing\_brain.pkl trực tiếp vào RAM nhằm tối ưu tốc độ truy xuất thuật toán.

---

## **2: Giao kèo API & Giao tiếp ngoại vi (API Contract & Interfaces)**

Đây là phần quan trọng nhất khi làm việc nhóm. Nếu phần này thiết kế sai hoặc mập mờ, lúc ráp code (Integration) chắc chắn sẽ gãy.

### **2.1. Thiết kế WebSocket (Cho Client \- Chat Server):**

* **Giải thích:** Định nghĩa các sự kiện (Events) đẩy qua lại. Ví dụ: Sự kiện Client gửi tọa độ lên (location.sent) payload trông như thế nào. Sự kiện Server đẩy kết quả bản đồ về (routing.result.received) có định dạng JSON ra sao.

*Mục đích: Định nghĩa cách App Chat gửi/nhận tin nhắn tức thời.*

**Nội dung bộ khung:**

* **Protocol:** Sử dụng WSS (Secure WebSocket).  
* **Event Dictionary:** Liệt kê các sự kiện chính (ví dụ: msg\_send, msg\_receive, user\_typing, location\_share).  
* **Payload Format:** Quy định định dạng JSON chuẩn cho mỗi sự kiện để Client và Server Spring không bị lệch pha.

### **2.2. Thiết kế REST API nội bộ (Cho Chat Server \- AI Server):**

Phân hệ này sử dụng kiến trúc **Webhook / Asynchronous Callback**. Do việc tính toán đường đi của AI (Python) là tác vụ tốn thời gian (CPU-bound, mất từ 1-3 giây), Chat Server (Java) sẽ không giữ kết nối để chờ đợi nhằm tránh nghẽn luồng.

Quy chuẩn đặt tên (Naming Convention) được thống nhất là **camelCase**. Bắt buộc truyền Header x-internal-api-key ở mọi request để bảo mật giữa các microservices.

**A. Endpoint Tìm đường (*Java* gọi Python):**

* **Mô tả:** Server Java gửi tọa độ và yêu cầu AI tính toán lộ trình.   
  **Method:** POST /api/v1/ai/routing   
* **Input:** Tọa độ điểm đầu/cuối (lat, lon), ID người dùng, ID cuộc hội thoại  
* **Authentication:** Thống nhất dùng API-KEY hoặc Bearer Token nội bộ để tránh người lạ gọi trực tiếp vào lõi AI của bạn.  
* **Headers:**   
  * Content-Type: application/json  
  * x-internal-api-key: \<SECRET\_KEY\>  
* **Cấu trúc:**

| {  "userId": "app\_user\_001",  "conversationId": "uuid\_của\_cuộc\_hội\_thoại",  "platform": "app",  "callbackUrl": "https://api.domain-cua-ban-kia.com/api/callback/routing",  "origin": {    "lat": 10.762622,    "lng": 106.660172  },  "destination": {    "lat": 10.776111,    "lng": 106.701222  }, } |
| :---- |

* **Phản hồi (Response):**   
  * **Status Code:** 202 Accepted (Báo hiệu: "Đã nhận yêu cầu, đang xử lý ngầm")  
  * **Body:**

| {   "status": "processing",   "message": "Routing calculation started in background." } |
| :---- |

![][image2]

Mermaid Syntax Code

| sequenceDiagram     autonumber     actor Client as User (Mobile/Web)     participant Java as Java Server (Chat/Gateway)     participant Redis as Redis Cache (Java)     participant Python as FastAPI (AI Routing Bot)     participant DB as MongoDB Atlas & Disk (AI)     Client-\>\>Java: Gửi tin nhắn xin đường (WSS: route.request)     Java-\>\>Redis: Check Cache lộ trình (Cache Miss)          rect rgb(235, 248, 255\)         Note right of Java: API 1: Lõi AI Nhận yêu cầu         Java-\>\>Python: POST /api/v1/routing \<br/\>(Gửi Tọa độ \+ callbackUrl)         Python--\>\>Java: HTTP 202 Accepted \<br/\>{"status": "processing"}     end     Note over Java, Client: Luồng Java được giải phóng để đi phục vụ user khác          rect rgb(255, 245, 230\)         Note right of Python: Quá trình AI xử lý ngầm (asyncio.to\_thread)         Python-\>\>DB: Lấy dữ liệu bus\_speeds (MongoDB)         DB--\>\>Python: Trả về vận tốc Real-time         Python-\>\>Python: Map dữ liệu với master\_stops.json         Python-\>\>Python: Chạy thuật toán A\* trên routing\_brain.pkl (RAM)         Python-\>\>DB: Lấy tọa độ đường cong (geometry\_store.feather từ Disk)         DB--\>\>Python: Trả về Coordinates         Python-\>\>Python: Đóng gói GeoJSON & Link ảnh     end     rect rgb(235, 255, 235\)         Note right of Python: API 2: Lõi AI Trả kết quả (Webhook)         Python-\>\>Java: POST vào {callbackUrl} \<br/\>(Payload: GeoJSON, Warnings, Images)         Java--\>\>Python: HTTP 200 OK     end     Java-\>\>Redis: Lưu lộ trình vào Cache (TTL 5 mins)     Java-\>\>Client: Trả kết quả (WSS: route.response)  |
| :---- |

**B. Cơ chế Callback (Python trả kết quả cho *Java*):**

* **Mô tả:** Khi thuật toán A\* tính xong, Server Python đóng gói kết quả thành định dạng tin nhắn chuẩn và chủ động gọi ngược (POST) vào callbackUrl mà Java đã cung cấp   
* **Endpoint:** POST /api/callback/routing   
* **Headers:**  
  * **Content-Type: application/json**  
  * **x-internal-api-key: \<SECRET\_KEY\>**  
* **Cấu trúc:**

| {   "conversationId": "uuid", // Từ session\_id hoặc do Chat Server truyền sang lúc gọi AI   "senderId": BOT\_ID, // Dùng số 0 hoặc "BOT\_ID" cố định để Chat Server hiểu đây là tin nhắn hệ thống/Bot   "role": "BOT", // Để Frontend dễ render UI   "type": "ROUTE\_SUGGESTION", // Phân loại tin nhắn chuyên biệt cho định tuyến   "text": "Lộ trình tối ưu qua các hẻm né kẹt xe đã sẵn sàng.", // Tương đương "instruction" trong PRD cũ      "metadata": {     "route": {       "distance\_km": 5.2, // Có thể tính toán từ AI       "estimated\_time\_mins": 15, // Thời gian dự kiến       "geojson": {         "type": "LineString",         "coordinates": \[\[106.701, 10.776\], \[106.702, 10.778\]\] // Nếu Client muốn tự vẽ bản đồ       },       "navigation\_url": "https://www.google.com/maps/dir/..." // Link Google Maps gốc     },     "warnings": \["Đang kẹt xe ở ngã tư Hàng Xanh"\] // Cảnh báo thêm nếu có   },   // MỚI: Tích hợp ảnh bản đồ tĩnh vào mảng "attachments" chuẩn của Chat Server   "attachments": \[     {       "type": "IMAGE",       "url": "https://huggingface.co/.../map.png", // Ảnh chụp tĩnh do AI sinh ra (Folium)       "width": 1080,       "height": 720,       "size": 204800     }   \],   "status": "SENT" } |
| :---- |

* **Phản hồi (Response):**  
  * **Status Code:** 200 OK (Java xác nhận đã nhận tin nhắn và lưu vào MongoDB thành công).  
  * **Body:** 

| {"status": "success"} |
| :---- |

### **2.3. Tích hợp Ngoại vi (External Integrations):**

Phân hệ AI dựa vào hai nguồn dữ liệu ngoại vi cốt lõi: Dữ liệu giao thông thời gian thực (API Buyttphcm) và Dữ liệu mạng lưới giao thông (OpenStreetMap). Nhằm bảo vệ hệ thống trước sự cố mạng và tiết kiệm tài nguyên, các tương tác này đều được thiết kế chạy ngầm hoặc tải trước (Pre-fetch).

#### **A. Giao tiếp API Xe buýt (Buyttphcm Crawler)**

Hệ thống sử dụng cơ chế cào dữ liệu (Crawling) bất đồng bộ thông qua mô hình **Producer-Consumer** (với hàng đợi asyncio.Queue) bằng thư viện httpx.

**Vượt rào cản mạng (Proxy Tunneling):**

* **Thách thức:** Server AI được đặt tại Hugging Face Spaces (Cloud quốc tế), trong khi hệ thống Buyttphcm chặn dải IP nước ngoài (trả về lỗi 403 Forbidden).  
* **Giải pháp:** Mọi request cào dữ liệu từ Server Python bắt buộc phải đi qua một **VN Proxy tĩnh**. Cấu hình Proxy được quản lý bảo mật qua biến môi trường .env (VN\_PROXY) và truyền vào httpx.AsyncClient tại thời điểm khởi tạo luồng Crawler.

**Chiến lược thu thập (Crawl Strategy):**

* **Tránh vét cạn (Anti Brute-force):** Thay vì gọi hàng trăm ngàn request vô ích, hệ thống chỉ ghép nối các ID tuyến, chiều và trạm thực sự có xe đang chạy.  
* **Endpoint API 2 (Dự đoán xe đến):** GET /{route\_id}/{dir}/{stop\_id}/predictnextstops/3  
* **Xử lý Dữ liệu:** Khi API trả về thời gian dự kiến xe đến trạm tiếp theo, luồng Consumer sẽ tính toán vận tốc trung bình của đoạn đường thông qua công thức nội suy v \= dt. Kết quả này được "Upsert" trực tiếp vào MongoDB Atlas (Collection TrafficData) với chỉ mục tự hủy TTL 60 phút.

#### **B. Tích hợp Dữ liệu Bản đồ (OpenStreetMap \- OSMnx)**

Để triệt tiêu độ trễ mạng khi tìm đường, Server AI không gọi API bản đồ theo thời gian thực mà sử dụng cơ chế xử lý Offline.

**Chuẩn hóa dữ liệu (Offline Processing):**

* Sử dụng thư viện OSMnx và NetworkX để tải và trích xuất mạng lưới đường bộ của TP.HCM.  
* Hệ thống gán trọng số tĩnh (Static Heuristics) cho từng cạnh đồ thị (Ví dụ: đường nhánh hẻm residential có vận tốc mặc định là 20km/h) để phòng hờ trường hợp dữ liệu thời gian thực từ MongoDB bị mất (Cold Start).

**Kiến trúc nạp dữ liệu (Storage & Boot-up Strategy):** Dữ liệu bản đồ được lưu chung vào Docker Image và quản lý theo nguyên tắc Tách đôi (Split Architecture):

* **Bản lưu RAM (Hot Graph):** File routing\_brain.pkl chỉ chứa cấu trúc ID Node và trọng số khoảng cách. File này được nạp thẳng vào **RAM** ngay khi FastAPI khởi động, đảm bảo thuật toán A\* chạy mượt mà dưới 500MB RAM.  
* **Bản lưu Ổ cứng (Cold Geometry):** File geometry\_store.feather chứa toàn bộ tọa độ không gian (Geometry) phức tạp. FastAPI chỉ lấy file này từ **Disk** tại đúng mili-giây cuối cùng, khi cần lấy tọa độ GPS để đóng gói thành chuỗi GeoJSON trả về cho Server Java.

### **2.4. Định dạng dữ liệu trao đổi (Data Exchange Format) \- \[MỤC CHUNG\]**

*Mục đích: Thống nhất "ngôn ngữ" chung cho các dữ liệu phức tạp.*

Để đảm bảo tính nhất quán và dễ dàng mở rộng, mọi luồng giao tiếp dữ liệu giữa Client, Server Java và Server Python đều phải tuân thủ nghiêm ngặt các tiêu chuẩn định dạng dưới đây.

#### **A. Chuẩn dữ liệu Không gian (GeoJSON Standard)**

Hệ thống thống nhất sử dụng chuẩn **GeoJSON (RFC 7946\)** để biểu diễn dữ liệu bản đồ thay vì tự chế ra các mảng tọa độ tùy ý. Điều này giúp các thư viện Frontend (như Mapbox, Leaflet, Google Maps SDK) có thể render (vẽ) đường đi ngay lập tức mà không cần viết thêm hàm parse (chuyển đổi) dữ liệu.

* **Cấu trúc áp dụng:** Sử dụng đối tượng LineString cho lộ trình.  
* **Quy tắc sinh tử (Cần lưu ý Frontend):** Theo chuẩn GeoJSON, mảng tọa độ bắt buộc phải theo thứ tự **\[Kinh độ (Longitude), Vĩ độ (Latitude)\]**. *(Lưu ý: Ngược với thói quen đọc Lat/Lng thông thường)*.  
* **Ví dụ chuẩn:**

| "geojson": {   "type": "LineString",   "coordinates": \[     \[106.660172, 10.762622\], // \[Lng, Lat\] của điểm A     \[106.665000, 10.768000\], // \[Lng, Lat\] điểm trung gian     \[106.701222, 10.776111\]  // \[Lng, Lat\] của điểm B   \] } |
| :---- |

#### **B. Quy chuẩn Thời gian (Time Standard)**

Mọi trường dữ liệu liên quan đến thời gian (createdAt, updatedAt, timestamp cào dữ liệu xe buýt) đều phải sử dụng định dạng **ISO 8601 theo múi giờ UTC (Z)**. Client App sẽ tự chịu trách nhiệm convert sang múi giờ địa phương (VD: UTC+7 cho Việt Nam) khi hiển thị cho người dùng.

* **Ví dụ:** "2026-05-09T06:31:36.429Z"

**C. Bảng Mã Lỗi Hệ Thống (Standardized Error Codes)**

HTTP Status Code dùng cho tầng giao thức (transport)

Error Code dùng cho logic nghiệp vụ (business)

Mỗi lỗi có code duy nhất toàn hệ thống

Có thể dùng chung giữa Chat Server (Java) và AI Service (Python)

| Error Code | Tầng phát sinh | HTTP Status | Mô tả | Fallback / Xử lý |
| ----- | ----- | ----- | ----- | ----- |
| ERR\_ROUTE\_OUT\_OF\_BOUNDS | AI Service (Python) | 400 Bad Request | Tọa độ nằm ngoài phạm vi hỗ trợ (ví dụ ngoài TP.HCM) | Yêu cầu user chọn lại điểm hợp lệ |
| ERR\_ROUTE\_NO\_PATH | AI Service (Python) | 422 Unprocessable Entity | Không tìm thấy đường đi hợp lệ giữa 2 điểm (A\* failure) | Trả thông báo không có tuyến khả dụng |
| ERR\_TRAFFIC\_DATA\_UNAVAILABLE | AI Service (Python) | 503 Service Unavailable | Không truy cập được dữ liệu giao thông (API/crawler lỗi) | Dùng mô hình vận tốc mặc định \+ warning |
| ERR\_AI\_PROCESSING\_FAILED | AI Service (Python) | 500 Internal Server Error | Lỗi nội bộ khi xử lý thuật toán (graph, memory, A\*) | Log lỗi \+ trả failure response |
| ERR\_AI\_TIMEOUT | Chat Server (Java) | 504 Gateway Timeout | AI không phản hồi callback trong thời gian quy định | Ngắt trạng thái chờ \+ báo hệ thống bận |
| ERR\_INTERNAL\_JAVA | Chat Server (Java) | 500 Internal Server Error | Lỗi backend Java (NullPointer, DB error, runtime exception) | Log hệ thống \+ trả lỗi generic |
| ERR\_DATABASE\_CONNECTION\_FAILED | Chat Server (Java) | 503 Service Unavailable | Không kết nối được PostgreSQL / MongoDB / Redis | Retry \+ degraded mode |
| ERR\_WEBSOCKET\_DISCONNECTED | Chat Server (Java) | 4000 (internal event) | WebSocket bị ngắt kết nối đột ngột | Client tự reconnect \+ restore session |
| ERR\_AUTH\_UNAUTHORIZED | Shared | 401 Unauthorized | Sai hoặc thiếu API Key / JWT khi gọi service | Reject request ngay lập tức |
| ERR\_AUTH\_FORBIDDEN | Shared | 403 Forbidden | Không có quyền truy cập tài nguyên | Chặn truy cập \+ log security event |
| ERR\_RATE\_LIMIT\_EXCEEDED | Chat Server / Gateway | 429 Too Many Requests | Gửi request quá nhanh vượt giới hạn | Throttle \+ retry-after |
| ERR\_DEPENDENCY\_UNAVAILABLE | Chat Server / AI Service | 503 Service Unavailable | Service phụ thuộc (Redis/API/AI/DB) bị lỗi | Circuit breaker \+ fallback mode |

---

## **3: Thiết kế Dữ liệu (Data Design)**

Mô tả cách thức lưu trữ tĩnh (Disk) và động (RAM).

### **3.1. Relational Schema (PostgreSQL cho Hệ thống Chat):**

* **Giải thích:** Vẽ ERD (Sơ đồ quan hệ thực thể) hoặc liệt kê các bảng chính: Users, Conversations, Messages. Chỉ ra rõ khóa chính, khóa ngoại. Đặc biệt chú ý cấu trúc trường payload (thường dùng kiểu JSONB trong Postgres) trong bảng Messages để lưu được linh hoạt tọa độ GPS hoặc Link bản đồ.

*Mục đích: Lưu trữ thông tin người dùng và lịch sử nhắn tin ổn định trên PostgreSQL.*

**3.1. Relational Schema (PostgreSQL \- Chat System)**

**Công nghệ**

PostgreSQL

Spring Data JPA (Hibernate)

**Mục tiêu**

Lưu trữ dữ liệu quan hệ của hệ thống chat bao gồm:

Người dùng (Users)

Phòng chat (Conversations)

Thành viên phòng chat (Conversation Members)

Trạng thái gửi/đọc tin nhắn (Message Receipts)

**ERD Logic** 

Users (1) ──────── (N) Conversation\_Members ──────── (1) Conversations

Users (1) ──────── (N) Message\_Receipts (via message\_id)

Conversations (1) ─ (N) Messages (lưu ở MongoDB)

**Bảng USERS** 

| Field | Type | Constraint | Mô tả |
| ----- | ----- | ----- | ----- |
| id | BIGSERIAL | PK | ID người dùng |
| username | VARCHAR(50) | UNIQUE, NOT NULL | Tên đăng nhập |
| password | VARCHAR(255) | NOT NULL | Mật khẩu đã hash |
| avatar | TEXT | NULL | Ảnh đại diện |
| last\_seen | TIMESTAMP | NULL | Thời gian hoạt động gần nhất |
| created\_at | TIMESTAMP | DEFAULT NOW() | Thời gian tạo tài khoản |

**Bảng CONVERSATIONS** 

| Field | Type | Constraint | Mô tả |
| ----- | ----- | ----- | ----- |
| id | BIGSERIAL | PK | ID phòng chat |
| type | VARCHAR(20) | CHECK (PRIVATE, GROUP) | Loại phòng chat |
| name | VARCHAR(100) | NULL | Tên nhóm (nếu GROUP) |
| last\_message\_id | VARCHAR(64) | NULL | ID message (MongoDB reference) |
| created\_at | TIMESTAMP | DEFAULT NOW() | Thời gian tạo |

**Bảng CONVERSATION\_MEMBERS** 

| Field | Type | Constraint | Mô tả |
| ----- | ----- | ----- | ----- |
| conversation\_id | BIGINT | PK, FK → conversations | ID phòng chat |
| user\_id | BIGINT | PK, FK → users | ID người dùng |
| role | VARCHAR(20) | DEFAULT MEMBER | OWNER / ADMIN / MEMBER |
| joined\_at | TIMESTAMP | DEFAULT NOW() | Thời gian tham gia |

 Primary Key kép:

(conversation\_id, user\_id)

Mục đích:

* quản lý user trong group chat  
* hỗ trợ role-based permission

**Bảng MESSAGE\_RECEIPTS** 

| Field | Type | Constraint | Mô tả |
| ----- | ----- | ----- | ----- |
| message\_id | VARCHAR(64) | PK | ID message (MongoDB ObjectId) |
| user\_id | BIGINT | PK, FK → users | Người nhận |
| delivered\_at | TIMESTAMP | NULL | thời điểm nhận message |
| read\_at | TIMESTAMP | NULL | thời điểm đã đọc |

Primary Key kép:

(message\_id, user\_id)

 Mục đích:

* tracking trạng thái tin nhắn  
* support delivered / read receipts (giống Messenger, Zalo)

**INDEXES (Tối ưu hiệu năng)** 

| Index | Mục đích |
| ----- | ----- |
| idx\_members\_user | tìm tất cả phòng chat của user |
| idx\_receipts\_user | truy vấn trạng thái đọc của user |
| idx\_conversations\_last\_message | load chat preview nhanh |

# **3.2. MongoDB Schema (Messages Layer)**

## **📍 Công nghệ**

* Spring Data MongoDB

## **📊 Collection: messages**

{

 "\_id": "ObjectId",

 "conversationId": "uuid",

 "senderId": "uuid",

 "role": "USER | BOT | SYSTEM",

 "type": "TEXT | IMAGE | ROUTE\_SUGGESTION",

 "content": "Hello",

 "metadata": {

   "route": {},

   "geojson": {},

   "warnings": \[\]

 },

 "attachments": \[

   {

     "type": "IMAGE",

     "url": "https://...",

     "width": 1080,

     "height": 720

   }

 \],

 "createdAt": "2026-05-14T06:31:36.429Z"

}

## **Lý do dùng MongoDB cho Messages**

* dữ liệu chat rất lớn (high write throughput)  
* schema thay đổi liên tục  
* metadata linh hoạt (AI response)  
* tối ưu cho realtime logging

# **3.3. Redis Cache Layer (Realtime Routing Cache)**

## **Công nghệ**

* Spring Data Redis

# **3.3. Redis Cache Layer (Realtime Routing Cache)**

## **Công nghệ**

* **Spring Data Redis**

## **Cache key design**

**route:{origin\_lat}\_{origin\_lng}\_{dest\_lat}\_{dest\_lng}**

**Ví dụ:**

**route:10.762622\_106.660172\_10.776111\_106.701222**

## **Cache value**

**{**

 **"distance\_km": 5.2,**

 **"eta\_min": 15,**

 **"geojson": {...},**

 **"cached\_at": "2026-05-14T06:31:36.429Z"**

**}**

## **TTL Policy**

| Loại dữ liệu | TTL |
| ----- | ----- |
| **Route result** | **5 phút** |

## **Logic hoạt động**

1. **User request route**  
2. **Check Redis cache trước**  
3. **Nếu HIT → trả ngay**  
4. **Nếu MISS → gọi AI Python**  
5. **Lưu kết quả vào Redis (TTL \= 5 phút)**

##  **Lợi ích Redis layer**

* **giảm tải AI service**  
* **giảm latency routing**  
* **tối ưu traffic spike (giờ cao điểm)**

### **3.2. NoSQL Schema (MongoDB cho Dữ liệu Giao thông):**

Phân hệ AI hoạt động hoàn toàn độc lập, sở hữu một cơ sở hạ tầng lưu trữ riêng biệt để phục vụ việc cào dữ liệu (Crawling), tính toán kẹt xe và phân tích lịch sử. Hệ thống áp dụng chiến lược phân tầng dữ liệu (Tiered Storage) để tối ưu chi phí và hiệu năng.

#### **A. Kiến trúc Lưu trữ Phân tầng (Tiered Storage Architecture)**

Dữ liệu giao thông được luân chuyển qua hai cấp độ lưu trữ:

1. **Kho Nóng (Hot Storage) \- MongoDB Atlas M0 (512MB):** Chỉ dùng để lưu trữ dữ liệu kẹt xe tức thời (Real-time). Phục vụ trực tiếp cho thuật toán tìm đường A\* có khả năng né điểm kẹt xe với độ trễ thấp nhất.  
2. **Kho Lạnh (Cold Storage) \- Disk Hugging Face Spaces (50GB):** Tận dụng ổ cứng cục bộ miễn phí của Hugging Face để lưu trữ dữ liệu thống kê lịch sử. Dữ liệu cũ từ MongoDB sẽ được gom lại và lưu dưới định dạng nén siêu nhẹ **.parquet**, giúp lưu trữ hàng triệu bản ghi mà không lo cạn kiệt dung lượng.

#### **B. Thiết kế Kho Nóng (MongoDB Schema)**

Hệ thống áp dụng kỹ thuật Chuẩn hóa dữ liệu (Normalization) để tối ưu dung lượng. Cụ thể, các thông tin tĩnh của trạm xe buýt (Tên, Tọa độ, Tuyến) được tách ra và quản lý trên RAM, do đó Collection trên MongoDB chỉ lưu trữ các thông tin động tối thiểu. 

**Collection bus\_speeds**

Lưu trữ vận tốc hiện tại tại các trạm xe buýt, được sinh ra từ luồng Crawler.

* **Schema Example (Dữ liệu động):** 

| {   "\_id": {     "$oid": "69fed5d7b9fcfe42573917f9"   },   "timestamp": {     "$date": "2026-05-09T06:31:36.429Z"   },   "next\_stop\_id": "312", // Khóa ngoại (Foreign Key) liên kết với master\_stops.json    "speed\_ms": 4.89 // Vận tốc đo được (đơn vị: mét/giây) }  |
| :---- |

* **Chiến lược Tối ưu hóa (TTL Index):** Để đảm bảo gói MongoDB Atlas 512MB không bao giờ bị đầy, hệ thống thiết lập chỉ mục Time-To-Live.  
  * db.bus\_speeds.createIndex({ "timestamp": 1 }, { expireAfterSeconds: 86400 })  
  * *Tác dụng:* Dữ liệu vận tốc cũ hơn 24 giờ sẽ bị bốc hơi tự động. Điều này vừa giúp tiết kiệm dung lượng, vừa đảm bảo AI không lấy nhầm dữ liệu kẹt xe "cũ rích" từ ngày trước để tính toán.

### **3.3. In-Memory Data (Quản lý RAM cho AI):**

Dữ liệu mạng lưới giao thông TP.HCM rất nặng, do đó áp dụng **Kiến trúc Tách đôi (Split Architecture)** để tối ưu RAM cho Container FastAPI trên Hugging Face.

* **Phần Nổi (RAM \- Hot Graph):** Lưu trữ file routing\_brain.pkl (chỉ chứa ID node, cấu trúc liên kết và chiều dài). Nạp thẳng vào **RAM** lúc server khởi động. Thuật toán A\* chạy trực tiếp trên vùng nhớ này, đảm bảo dung lượng tiêu thụ dưới 500MB. **File master\_stops.json (Lookup Dictionary):** Hoạt động như một bảng từ điển tra cứu nhanh. Khi thuật toán đọc next\_stop\_id từ MongoDB, nó sẽ map (ánh xạ) với file này để lấy Lat, Lng và Name tương ứng nhằm định vị điểm kẹt xe trên đồ thị.   
* **Phần Chìm (Disk \- Cold Geometry):** Lưu trữ file geometry\_store.feather (chứa tọa độ chi tiết làm mượt đường cong). Nằm yên trên **ổ cứng**. Thuật toán chỉ truy xuất file này ở *mili-giây cuối cùng* sau khi đã tìm xong lộ trình để vẽ GeoJSON.

### **3.4. Cache Strategy (Chiến lược bộ nhớ đệm) \- \[MỤC CHUNG\]**

*Mục đích: Giảm tải cho Server AI khi nhiều người hỏi cùng một lộ trình.*

**Global Cache (Redis):** Lưu các kết quả tìm đường phổ biến giữa các quận/huyện.

**Local Cache:** Giảm tải tính toán dư thừa cho thuật toán A\* bằng thư viện cachetools.TTLCache.

* **Cơ chế:** Cache lại kết quả GeoJSON đầu ra của hàm find\_shortest\_path. Nếu có request tìm đường trùng khớp cặp tọa độ xuất phát \- đích trong vòng **5 phút**, Server Python sẽ trả ngay kết quả từ RAM mà không cần tính toán lại.

---

## **4: Luồng nghiệp vụ chi tiết (Operational Scenarios / Flows)**

Phần này mô tả hệ thống "động" đậy như thế nào theo thời gian.

### **4.1. Luồng Tìm đường Cốt lõi (Core Routing Flow) \- \[MỤC CHUNG\]**

*Mục đích: Kịch bản "Đường màu hồng" (Happy Path) khi người dùng yêu cầu chỉ đường và hệ thống hoạt động hoàn hảo.*

**Các bước thực thi (Giao kèo cho Sequence Diagram):**

1. **Client gửi Yêu cầu:** Người dùng trên App/Web nhấn nút "Tìm đường", Client gửi event chứa cặp tọa độ origin và destination qua WebSocket tới **Chat Server (Java)**.  
2. **Kiểm tra Cache (Java):** Java Server check **Redis Cache**.  
   1. *Nếu Cache HIT (Tuyến này vừa có người tìm):* Java lấy ngay kết quả GeoJSON từ Redis, nhảy thẳng tới Bước 7\.  
   2. *Nếu Cache MISS:* Đi tiếp Bước 3\.  
3. **Java giao việc cho AI:** Java gọi HTTP POST /api/v1/routing sang **AI Server (Python)**, đính kèm callbackUrl của Java.  
4. **AI phản hồi tức thì:** Python tiếp nhận request và lập tức trả về HTTP 202 Accepted. Luồng của Java được giải phóng ngay lập tức để tiếp tục xử lý các tin nhắn chat khác (Không bị block).  
5. **AI Xử lý ngầm (Python):** Hàm tìm đường được đẩy ra luồng phụ (asyncio.to\_thread):  
   1. Đọc dữ liệu bus\_speeds (vận tốc) mới nhất từ **MongoDB Atlas** (hoặc từ Local Cache cachetools).  
   2. Áp dụng trọng số kẹt xe lên đồ thị (đã nạp sẵn trong RAM) và chạy thuật toán $A^\*$.  
   3. Đọc file geometry\_store.feather từ ổ cứng để lấy tọa độ chi tiết làm mượt đường đi.  
6. **AI trả kết quả (Webhook):** Sau 1-2 giây tính toán xong, Python chủ động gọi ngược HTTP POST vào callbackUrl của Java, truyền đi Payload chứa metadata.geojson và attachments (ảnh bản đồ tĩnh).  
7. **Trả về Client:** Java nhận kết quả, lưu lịch sử tin nhắn vào MongoDB của Java, lưu kết quả bản đồ vào Redis (TTL 5 phút), và đẩy tin nhắn dạng ROUTE\_SUGGESTION qua WebSocket về Client hiển thị.

### **4.2. Luồng Xử lý Lỗi & Dự phòng (Fallback Handling) \- \[MỤC CHUNG\]**

*Mục đích: Kế hoạch tác chiến khi có sự cố, đảm bảo App Chat không bao giờ bị "treo" hay sập dây chuyền.*

**A. Kịch bản: AI Server quá tải (Timeout \> 3s)**

* **Vấn đề:** Python tính toán quá lâu hoặc đứt mạng nội bộ.  
* **Giải pháp:** Phía **Java** set một timer đếm ngược 3 giây. Nếu quá 3s chưa nhận được Webhook từ Python, Java tự động hủy chờ và gửi tin nhắn về cho Client: *"Trợ lý AI hiện đang xử lý quá nhiều yêu cầu. Vui lòng thử lại sau ít phút\!"*.

**B. Kịch bản: Mất dữ liệu Giao thông (Cold Start / Crawler Down)**

* **Vấn đề:** API Buyttphcm bảo trì, MongoDB Atlas của AI bốc hơi hết dữ liệu (do TTL Index) và trở nên trống rỗng.  
* **Giải pháp:** Thuật toán $A^\*$ của **Python** tự động Fallback. Nó bỏ qua MongoDB và tính toán lộ trình dựa trên **Trọng số tĩnh (Static Heuristics)** (Ví dụ: hẻm residential đi với vận tốc mặc định 20km/h). Trong kết quả trả về, Python đính kèm cảnh báo vào biến warnings: *"Dữ liệu kẹt xe hiện không khả dụng, lộ trình được tính toán dựa trên khoảng cách."*

### **4.3. Luồng Chạy ngầm (Background Jobs Pipeline):**

* **Giải thích:** Sơ đồ riêng cho Crawler cào dữ liệu xe buýt (mỗi 5 phút/lần) chạy độc lập với luồng nhắn tin của người dùng.

*Mục đích: Đảm bảo kho dữ liệu kẹt xe luôn tươi mới mà không làm ảnh hưởng luồng Chat.*

**Các bước thực thi:**

1. Một Vòng lặp sự kiện ngầm (Background Task) tự động kích hoạt mỗi 5 phút/lần.  
2. Crawler (dùng httpx) đi qua **Proxy Việt Nam** để lách lỗi 403, gọi vào API của Buyttphcm.  
3. Chắt lọc các tuyến xe buýt đang chạy, tính toán vận tốc speed\_ms.  
4. Ghi đè trực tiếp (Upsert) dữ liệu vào Collection bus\_speeds trên MongoDB Atlas để làm mới mốc thời gian của TTL Index, giúp dữ liệu sống thêm 60 phút.  
5. Cuối mỗi ngày, một Cronjob chạy ngầm sẽ nén các dữ liệu cũ thành file .parquet và lưu vào ổ cứng Hugging Face (Kho Lạnh) phục vụ phân tích sau này.

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,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>