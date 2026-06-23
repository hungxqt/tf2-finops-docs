# Phân tích Chi phí (Cost Analysis) - TF2 FinOps Watch CDO06

<!-- Chủ tài liệu: CDO06
     Trạng thái: Draft W11 Pack #1, cập nhật dữ liệu thực tế W12 T4 Pack #2
     Phạm vi: Chi phí nền tảng CDO lakehouse-centric scheduled FinOps control plane -->

## 1. Mô hình Chi phí theo Tenant và Chu kỳ Chạy (Dự báo)

Một "tenant" trong ngữ cảnh TF2 FinOps Watch là một tài khoản thành viên AWS được giám sát chi phí. Mô hình chi phí phân tách chi phí biến đổi trên mỗi tenant khỏi chi phí nền tảng dùng chung. Sự phân biệt này rất quan trọng vì lakehouse và Lambda workflow chủ yếu mở rộng theo số lượng tài khoản/dữ liệu, trong khi EKS, mạng nội bộ và giám sát cơ sở tạo ra chi phí cố định dùng chung cần được phân bổ khấu hao trên các tenant.

CDO sở hữu chi phí lưu trữ vận hành của AI Engine do AIOps cung cấp trên EKS: control plane, managed node groups, ECR, công khai dịch vụ nội bộ (internal service exposure), IRSA, cấu hình secrets, autoscaling và giám sát runtime. AIOps sở hữu việc phát triển mô hình, thiết kế huấn luyện mô hình, chất lượng mô hình và bất kỳ bộ dữ liệu lịch sử tổng hợp nào được sử dụng để huấn luyện, cải tiến hoặc backtest mô hình. Nếu các job huấn luyện hoặc huấn luyện lại của AIOps chạy trên cụm EKS do CDO host, chi phí tính toán phải được gắn tag và báo cáo riêng là "chi phí workload AI Engine do CDO host".

| Thành phần | Đơn giá | Mức sử dụng trung bình dự kiến | Xử lý chi phí |
|---|---|---|---|
| **Compute - Lambda adapters** | $0.20/1M requests + $0.0000166667/GB-second | Puller, normalizer, router, containment, audit writer; chu kỳ 24h | Biến đổi theo tenant; `Cần bằng chứng: đo lường Lambda GB-giây`. |
| **Orchestration - Step Functions Standard** | $0.025/1K state transitions | 1 workflow/ngày/tài khoản, bao gồm cả thử lại | Biến đổi theo tenant; thấp nhưng phải đo lường với số lượng state thực tế. |
| **Orchestration - EventBridge Scheduler** | $1.00/1M invocations | 1 trigger theo lịch/ngày cộng với chạy lại thủ công (redrive) | Chi phí dùng chung không đáng kể. |
| **Storage - S3 raw/curated** | $0.023/GB-month Standard, thấp hơn sau lifecycle | Kéo CUR/Cost Explorer, parquet chuẩn hóa, trích xuất dashboard | Biến đổi theo dung lượng dữ liệu hóa đơn. |
| **Storage - S3 audit archive** | $0.0125/GB-month ước tính IA | Containment và bằng chứng quyết định lưu giữ ít nhất 90 ngày | Biến đổi theo dung lượng cảnh báo/containment; việc lưu trữ là bắt buộc. |
| **Database - DynamoDB on-demand** | $1.25/triệu write + $0.25/triệu read | Run state, idempotency, chỉ mục kiểm toán, dashboard materialized view | Biến đổi theo các lượt chạy và lượt đọc dashboard. |
| **Query - Athena** | $5.00/TB scanned | Refresh dashboard, tra cứu bằng chứng, xem xét vận hành | Biến đổi; được kiểm soát bởi partition pruning và giới hạn truy vấn. |
| **Data Catalog - Glue** | Phí catalog/crawler theo đối tượng và DPU-giờ | Bảng chi phí, phân vùng, tiến hóa schema | Biến đổi nhưng nhỏ ở quy mô capstone. |
| **EKS control plane** | Khoảng $0.10/giờ | Một cụm private cho AI Engine hosting | Chi phí cố định dùng chung, khoảng $73/tháng trước khi tính đến dung lượng sử dụng. |
| **EKS on-demand node group** | Giá EC2 on-demand theo loại thực thể | `ai-engine-api`, `ai-engine-explainer`, giám sát, hỗ trợ ingress/controller | Baseline cố định dùng chung; `Cần bằng chứng: loại thực thể được chọn và kích thước tối thiểu`. |
| **EKS spot node group** | Giá Spot EC2 theo loại thực thể | `ai-engine-worker`, batch scoring, kỹ nghệ đặc trưng, job huấn luyện lại | Chi phí host workload AI biến đổi; gắn tag riêng biệt khỏi CDO adapter. |
| **EKS node EBS volumes** | EBS GB-tháng | Volume gốc và lưu trữ job tạm thời | Dùng chung/biến đổi phụ thuộc vào định cỡ node và checkpoint của job. |
| **ECR repositories** | $0.10/GB-tháng lưu trữ | Hình ảnh container AIOps có phiên bản và container Lambda nếu sử dụng | Dùng chung cố định/biến đổi theo số lượng image được lưu giữ. |
| **Internal ALB/NLB** | Sử dụng hàng giờ + LCU/NLCU | Endpoint AI Engine riêng tư | Dùng chung cố định cộng với biến đổi theo request. |
| **VPC endpoints** | Phí endpoint hàng giờ + xử lý dữ liệu nếu áp dụng | S3, DynamoDB, ECR, Secrets Manager, CloudWatch Logs, KMS/STS khi cần thiết | Chi phí bảo mật cố định dùng chung. |
| **Secrets Manager** | $0.40/bí mật/tháng + phí request | API key của AI Engine, webhook, khóa ký hợp đồng, ID bên ngoài | Dùng chung cố định cộng với lượng request. |
| **KMS** | $1.00/CMK/tháng + phí request | Dữ liệu, kiểm toán, secrets, các khóa EBS volume của EKS node tùy chọn | Dùng chung cố định; việc hợp nhất yêu cầu phê duyệt của bộ phận Bảo mật. |
| **Observability - CloudWatch/Container Insights** | Phí Logs, metrics, dashboard và Container Insights | Lambda, Step Functions, EKS control plane, khả năng giám sát node và pod | Dùng chung và biến đổi; có thể trở thành nhân tố dẫn đầu về chi phí. |
| **Dashboard - QuickSight Reader** | Giá Reader/phiên | Bộ phận Tài chính truy cập dashboard | Dùng chung theo người dùng Finance, không theo dung lượng workload AI. |
| **Alerting - SNS/SES/Slack integration** | Phí request/tin nhắn | Định tuyến cảnh báo cho Finance và Engineering | Biến đổi nhưng dự đoán ở mức thấp. |
| **Total CDO platform forecast** | Hỗn hợp cố định và biến đổi | CDO infra cộng với AI Engine runtime do CDO host | `Cần bằng chứng: tính toán lại sau khi cấu hình node EKS, số lượng endpoint và khối lượng lượt chạy được chốt`. |

**Lưu ý quan trọng**:
- Dự báo trên là chi phí ước tính cho **hạ tầng nền tảng CDO** bao gồm nền tảng lưu trữ EKS do CDO sở hữu, nhưng không bao gồm việc phát triển mô hình và công việc chất lượng mô hình do AIOps sở hữu.
- EKS control plane, các nút on-demand baseline, VPC endpoint, ALB, KMS và khả năng quan sát là những chi phí cố định lớn nhất.
- Chi phí thực tế phải được đo lường từ chi tiêu AWS được gắn tag. Sử dụng `Cần bằng chứng: Chi phí thực tế EKS hosting của CDO`, `Cần bằng chứng: Chi phí thực tế trên mỗi lượt chạy của pipeline CDO` và `Cần bằng chứng: Chi phí thực tế của workload AI do CDO EKS host` cho đến khi đo lường được.

---

## 2. Chi phí theo Quy mô (Cost at Scale)

Khi số lượng tenant tăng, một số chi phí cố định (VPC Endpoints, KMS CMKs, QuickSight, EKS control plane) được phân bổ giữa nhiều tenant, giảm chi phí trung bình mỗi tenant. Phần này sử dụng cấu trúc dự báo thay vì tuyên bố kết quả đo lường thực tế.

| Số lượng Tenant | Chi phí cố định dùng chung/tháng | Chi phí biến đổi CDO workflow/tháng | Chi phí host AI workload/tháng | Tổng chi phí/tháng | Trung bình/tenant |
|---|---|---|---|---|---|
| **1** | `Cần bằng chứng: EKS baseline + endpoints` | `Cần bằng chứng: chi phí chạy 1 tài khoản` | `Cần bằng chứng: sử dụng AI worker` | `Cần bằng chứng` | `Cần bằng chứng` |
| **10** | Giữ nguyên baseline dùng chung | `Cần bằng chứng: chi phí chạy 10 tài khoản` | `Cần bằng chứng: sử dụng AI worker` | `Cần bằng chứng` | `Cần bằng chứng` |
| **50** | Baseline dùng chung cộng với mở rộng node nếu có | `Cần bằng chứng: chi phí chạy 50 tài khoản` | `Cần bằng chứng: sử dụng AI worker` | `Cần bằng chứng` | `Cần bằng chứng` |
| **200** | Baseline dùng chung cộng với giả định scale-out | `Cần bằng chứng: chi phí chạy 200 tài khoản` | `Cần bằng chứng: sử dụng AI worker` | `Cần bằng chứng` | `Cần bằng chứng` |

**Chi phí cố định bao gồm**:
- 4× VPC Interface Endpoints: $28.80
- 3× KMS CMKs: $3.00
- 1× QuickSight Reader (dùng chung): $5.00
- EKS control plane: khoảng $73.00/tháng
- Baseline on-demand node group: `Cần bằng chứng: loại thực thể × số lượng nút tối thiểu`
- Internal ALB/NLB: `Cần bằng chứng: load balancer được chọn và mức sử dụng LCU/NLCU`
- CloudWatch dashboard, logs, metrics, và Container Insights: `Cần bằng chứng: dung lượng nhật ký lưu giữ`

**Phân tích**:
- EKS làm cho chi phí cho một tenant cao hơn so với phiên bản serverless thuần túy, nhưng cùng một nền tảng đó hỗ trợ việc host API AI ổn định, các batch workers, khả năng quan sát và mạng riêng tư.
- Ở số lượng tenant lớn hơn, chi phí trung bình sẽ giảm xuống do EKS control plane, các nút baseline, các endpoint và chi phí dashboard được dùng chung.
- Điểm hòa vốn phải được tính toán lại sau khi biết kích thước nút EKS và hiệu suất sử dụng AI worker; không sử dụng lại ước tính cũ $46.77/tenant chỉ dành cho serverless.

---

## 3. Tối ưu hóa Chi phí đã Áp dụng

| Biện pháp tối ưu hóa | Trạng thái | Tiết kiệm ước tính | Ghi chú |
|---|---|---|---|
| **Lambda right-sizing** |  Implemented | 15-20% chi phí compute | Chạy benchmark để chọn 512MB thay vì 1024MB cho các worker |
| **S3 Lifecycle tiering** |  Implemented | 40% chi phí storage | Raw zone: Standard 7 ngày → IA 30 ngày → Glacier 90 ngày; Audit: IA sau 30 ngày |
| **DynamoDB on-demand** |  Implemented | 20% vs provisioned | Workload batch không đều, on-demand phù hợp hơn provisioned capacity |
| **Athena partition pruning** |  Implemented | 60-80% chi phí query | Phân vùng theo cost_period_start, account_id, service |
| **VPC Gateway Endpoints (S3, DynamoDB)** |  Implemented | $0.09/GB NAT cost | Lưu lượng S3/DDB không qua NAT Gateway |
| **CloudWatch Logs retention** |  Implemented | 50% chi phí logs | Application logs: 14 ngày; Audit logs: 90 ngày rồi chuyển S3 |
| **Lambda reserved concurrency** |  Not applicable | N/A | Workload batch tần suất thấp, không cần reserve |
| **Savings Plans / Reserved Instances** |  Đánh giá trong W12 T4 | 20-40% compute | Cần baseline 2 tuần để xác định cam kết; không áp dụng trong capstone 2 tuần |
| **Nhóm nút Spot cho AI workers** |  Đã triển khai trong thiết kế | 40-70% chi phí compute cho AI worker | Chỉ sử dụng cho `ai-engine-worker` có thể bị ngắt, scoring theo lô, kỹ nghệ đặc trưng và các job huấn luyện lại với checkpoint/retry. |
| **Định cỡ phù hợp nút On-demand** |  Cần bằng chứng | 15-30% EKS baseline | Chọn instance family ổn định nhỏ nhất hỗ trợ `ai-engine-api`, `ai-engine-explainer`, ingress, giám sát và core CDO pods. |
| **Tự động giảm quy mô bằng Karpenter hoặc Cluster Autoscaler** |  Đã triển khai trong thiết kế | 20-50% công suất worker | Loại bỏ dung lượng spot nhàn rỗi sau khi các job chạy theo lô hoàn thành. |
| **Cross-region replication** |  Out of scope | N/A | Single-region `ap-southeast-1`; DR design-only |
| **Bedrock prompt caching** |  Out of scope | N/A | AI inference cost thuộc về AIOps |

**Tổng kết**: Các biện pháp tối ưu hóa đã áp dụng giúp giảm chi phí so với baseline chưa tối ưu, nhưng tỷ lệ phần trăm chính xác là `Cần bằng chứng: đo lường dự báo tối ưu hóa so với không tối ưu hóa`. Ước tính chỉ dành cho serverless trước đây không còn giá trị vì CDO hiện sở hữu hạ tầng hosting EKS cho thời gian chạy AI Engine của AIOps.

---

## 4. So sánh Chi phí với các Góc độ khác (cùng Task Force)

Phần này so sánh hướng đi CDO06 hiện tại với các phương án thay thế phổ biến. Nó không khẳng định số liệu thực tế đo lường cuối cùng của các nhóm khác; chúng vẫn là khoảng trống bằng chứng cho đến khi tài liệu của họ khả dụng.

| Góc độ Kiến trúc | $/tenant/tháng (dự báo) | Lý do Khác biệt | Ghi chú |
|---|---|---|---|
| **CDO06: Lakehouse-centric scheduled + EKS-hosted AI Engine** | `Cần bằng chứng: chi phí thực tế nền tảng CDO sau định cỡ EKS` | Serverless orchestration giữ cho CDO adapter có chi phí thấp, trong khi EKS thêm chi phí hosting cố định cho AIOps runtime. | Trục chiến thắng: control plane FinOps có thể truy vết, private AI Engine hosting, containment an toàn và phân bổ chi phí nền tảng khi có quy mô. |
| CDO prototype thuần serverless | Chi phí cố định cho một tenant thấp hơn, nhưng không đầy đủ cho kịch bản hiện tại | Tránh chi phí EKS control plane và nút. | Bị từ chối vì kịch bản hiện tại yêu cầu host thời gian chạy AI Engine và các batch workload của CDO. |
| Tiếp cận nhà kho luôn bật (always-on) | Chi phí dữ liệu cố định cao hơn | Lưu trữ kiểu Redshift/RDS có thể đơn giản hóa một số SQL workflow nhưng tạo ra chi phí nhàn rỗi cho chu kỳ 24 giờ. | Bị từ chối vì S3/Glue/Athena phù hợp với bằng chứng FinOps hàng ngày với chi phí nhàn rỗi thấp hơn. |
| SaaS FinOps bên thứ ba | Phụ thuộc vào phí đăng ký | Có thể giảm việc vận hành nền tảng nhưng làm suy yếu ranh giới sở hữu CDO/AIOps và khả năng kiểm soát containment guardrail. | Không được chọn cho triển khai capstone. |

**Evidence cần thu thập để so sánh công bằng**:
- Chi phí kiểu tính toán (EKS on-demand/spot so với ECS so với Lambda so với EC2)
- Chi phí lưu trữ/truy vấn (RDS so với Redshift so với Athena so với EMR)
- Chi phí mạng (VPC peering, Transit Gateway, NAT Gateway)
- Chi phí vận hành (chi phí quản lý dịch vụ so với cụm tự quản lý)
- Phân chia việc host AI Engine (thời gian chạy nền tảng CDO so với phát triển/huấn luyện mô hình của AIOps)

---

## 5. Chi phí Thực tế Đo được (Measured Actual - Pack #2 W12 T4)

### 5.1 Chi phí Capstone 2 tuần

Phần này chỉ được điền sau khi chạy nền tảng với các tài nguyên AWS được gắn tag. CDO demo injection có thể được sử dụng cho smoke tests, nhưng bộ dữ liệu huấn luyện/backtest do AIOps sở hữu không được tính vào chi phí vận hành CDO trừ khi chúng chạy trên cụm EKS do CDO host.

| Dịch vụ | Dự báo (14 ngày) | Thực tế (14 ngày) | Chênh lệch | Ghi chú |
|---|---|---|---|---|
| Lambda adapters | `Cần bằng chứng: dự báo từ bộ nhớ/thời gian chạy` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Puller, normalizer, router, containment, audit writer. |
| Step Functions | `Cần bằng chứng: số lượng chuyển đổi trạng thái` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Bao gồm các lần thử lại và chạy lại thủ công. |
| S3 raw/curated/audit | `Cần bằng chứng: dự báo GB-tháng và request` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Tách biệt tiền tố dữ liệu chi phí và bằng chứng kiểm toán. |
| DynamoDB | `Cần bằng chứng: dự báo đọc/ghi` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Trạng thái chạy, idempotency, chỉ mục kiểm toán, materialized view của dashboard. |
| Athena/Glue | `Cần bằng chứng: TB đã quét và sử dụng crawler` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Xác thực việc loại bỏ phân vùng (partition pruning). |
| EKS control plane | Khoảng $34 cho 14 ngày | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Cố định khi cụm tồn tại. |
| Nút on-demand EKS | `Cần bằng chứng: loại thực thể × số lượng nút` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | API AI ổn định, explainer, giám sát, hỗ trợ ingress/controller. |
| Worker spot EKS | `Cần bằng chứng: số giờ job và loại thực thể` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Batch scoring, kỹ nghệ đặc trưng, job huấn luyện lại khi do CDO host. |
| ECR/EBS/Internal LB | `Cần bằng chứng: image lưu trữ, volume, LCU/NLCU` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Chi phí hỗ trợ host AI Engine. |
| VPC Endpoints | `Cần bằng chứng: số lượng endpoint × phí hàng giờ` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Truy cập dịch vụ AWS riêng tư. |
| CloudWatch/Container Insights | `Cần bằng chứng: dung lượng log và số custom metric` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Lambda, Step Functions, EKS, pods, nodes. |
| KMS/Secrets Manager | `Cần bằng chứng: số lượng CMK và secret` | `Cần bằng chứng: báo cáo tag Cost Explorer` | `Cần bằng chứng` | Dữ liệu, kiểm toán, secret của AI Engine, webhooks. |
| **Tổng cộng** | `Cần bằng chứng: tổng dự báo` | `Cần bằng chứng: tổng thực tế` | `Cần bằng chứng` | Không công bố số lượng cuối cùng cho đến khi được đo lường. |

**Phương pháp đo lường**:
1. Bật Cost Explorer với tag `Project=TF2-FinOps-CDO06` và `Environment=Sandbox`.
2. Chạy workflow tích hợp CDO 1 lần/ngày trong 14 ngày với các đầu vào demo được phê duyệt và containment dry-run.
3. Xuất AWS Cost and Usage Report sau 14 ngày, lọc theo tag.
4. Phân chia chi phí thành CDO adapter, baseline hosting EKS của CDO, thời gian chạy workload AI được host, lưu trữ/truy vấn, mạng và khả năng quan sát.
5. So sánh dự báo so với thực tế, phân tích các điểm dị biệt (outlier) và đánh dấu mọi giá trị chưa đo lường bằng `Cần bằng chứng: ...`.

### 5.2 Chi phí Thực tế theo Tenant

Sau khi onboard các tài khoản kiểm thử với các mức tải khác nhau:

| Tenant kiểm thử | Đặc điểm | Chi phí/ngày (thực tế) | Ngoại suy $/tháng | Ghi chú |
|---|---|---|---|---|
| Nhỏ | Số lượng account ít, CUR volume thấp, ít độc giả dashboard | `Cần bằng chứng` | `Cần bằng chứng` | Xác thực chi phí workflow tối thiểu. |
| Trung bình | Số lượng account trung bình, các dịch vụ dùng chung phổ biến, nhiều owner tag | `Cần bằng chứng` | `Cần bằng chứng` | Xác thực hình thái vận hành capstone mong đợi. |
| Lớn | Số lượng account cao hơn, CUR volume lớn hơn, hoạt động dashboard/truy vấn nặng hơn | `Cần bằng chứng` | `Cần bằng chứng` | Xác thực giới hạn quét Athena và khả năng mở rộng EKS worker. |

**Insight mong đợi**: Chi phí S3, Athena, DynamoDB và Lambda mở rộng theo số lượng tài khoản và dung lượng dữ liệu. EKS control plane và các nút on-demand baseline mở rộng dưới dạng chi phí nền tảng cố định dùng chung cho đến khi AI API hoặc hàng đợi worker yêu cầu thêm công suất.

### 5.3 Chi phí mỗi Quyết định Đúng (Cost-per-Correct-Decision)

Metric này đo lường hiệu quả chi phí của toàn bộ vòng quyết định FinOps Watch. CDO có thể báo cáo chi phí nền tảng CDO và chi phí thời gian chạy AI do CDO host, nhưng AIOps phải cung cấp các chỉ số chất lượng mô hình và bất kỳ chi phí phát triển mô hình nào họ muốn đưa vào.

| Chỉ số | Giá trị (dự báo) | Giá trị (thực tế W12) | Ghi chú |
|---|---|---|---|
| **Tổng số lượt gọi AI Engine** | `Cần bằng chứng: số lượt chạy lập kế hoạch × số lượng tài khoản` | `Cần bằng chứng` | Chỉ tính các cuộc gọi hợp đồng vận hành từ CDO tới AI Engine được host. |
| **Quyết định đúng** | Chỉ số do AIOps cung cấp | `Cần bằng chứng: kết quả đánh giá của AIOps` | CDO không tự tính toán từ dữ liệu huấn luyện của đội AI. |
| **Chi phí nền tảng CDO** | `Cần bằng chứng: tổng dự báo CDO` | `Cần bằng chứng` | CDO adapter, lakehouse, dashboard, alert, kiểm toán, baseline hosting EKS. |
| **Chi phí thời gian chạy AI trên EKS CDO** | `Cần bằng chứng: phân bổ chi phí nút worker/API` | `Cần bằng chứng` | Chỉ tính chi phí thời gian chạy, tách biệt với phát triển mô hình của AIOps. |
| **Chi phí phát triển mô hình AIOps** | Nằm ngoài phạm vi CDO trừ khi AIOps cung cấp | Do AIOps cung cấp | Tùy chọn cho ROI toàn bộ task-force, không phải là tuyên bố của CDO. |
| **Chi phí cho mỗi quyết định đúng** | `Cần bằng chứng` | `Cần bằng chứng` | = tổng chi phí đã thống nhất / số quyết định đúng do AIOps cung cấp. |

**So sánh benchmark**:
- Chi phí phát hiện bất thường thủ công: ~$200/bất thường (8 giờ × $25/giờ nhà phân tích Tài chính)
- Mục tiêu: Chi phí cho mỗi quyết định đúng phải duy trì thấp hơn đáng kể so với chi phí đánh giá thủ công sau khi AIOps cung cấp số lượng quyết định đúng và CDO cung cấp chi phí host/vận hành đo được.

---

## 6. Rào cản Chi phí (Cost Guardrails)

Để tránh chi phí vượt ngân sách trong quá trình capstone và demo:

| Guardrail | Ngưỡng | Hành động | Trách nhiệm |
|---|---|---|---|
| **Monthly budget alert 70%** | `Cần bằng chứng: ngân sách capstone có nhận biết EKS × 70%` | CloudWatch alarm -> SNS Engineering | Nhóm CDO xem xét các mẫu sử dụng |
| **Monthly budget alert 90%** | `Cần bằng chứng: ngân sách capstone có nhận biết EKS × 90%` | Alarm + email leo thang tới mentor | CDO + Mentor cùng xem xét |
| **Monthly budget hard stop 100%** | `Cần bằng chứng: ngân sách capstone được phê duyệt` | Vô hiệu hóa scheduler và chặn các job worker không thiết yếu | Fail-safe tự động ngăn ngừa chi phí tăng vọt |
| **Per-tenant S3 quota** | 100 GB/tenant curated data | S3 bucket quota + alarm | Ngăn ngừa bùng nổ dữ liệu của một tenant duy nhất |
| **Athena query daily limit** | 200 GB scanned/ngày | Service Quotas + alarm | Giới hạn chi phí truy vấn ad-hoc |
| **Lambda concurrent execution** | 10 concurrent | Reserved concurrency limit | Ngăn ngừa lambda storm |
| **DynamoDB WCU/RCU burst** | Auto-scaling max 100 | DynamoDB auto-scaling cap | Giới hạn chi phí bùng phát |
| **EKS on-demand baseline** | `Cần bằng chứng: số nút tối thiểu và số nút tối đa` | Cảnh báo về sự tăng trưởng baseline không mong đợi | Ngăn ngừa trôi chi phí (cost drift) của nhóm nút ổn định |
| **EKS spot worker runtime** | `Cần bằng chứng: số giờ chạy nút worker tối đa/ngày` | Dừng các job batch mới và cảnh báo CDO/AIOps | Ngăn ngừa chi phí batch/retraining tăng vọt |
| **Container Insights log volume** | `Cần bằng chứng: ngưỡng GB/ngày` | Giảm độ chi tiết hoặc rút ngắn retention sau khi được duyệt | Ngăn ngừa bùng phát chi phí observability |

**Dashboard giám sát**: CloudWatch dashboard `FinOpsWatch-CDO-CostGuardrails` hiển thị:
- Xu hướng chi tiêu hàng ngày (7 ngày gần nhất)
- Chi tiêu dự báo so với thực tế
- Top 5 nhân tố thúc đẩy chi phí (service breakdown, bao gồm EKS/EC2, ALB, VPC endpoints, CloudWatch, Athena)
- % sử dụng ngân sách
- Chi phí thời gian chạy AI được host tách biệt với chi phí phát triển mô hình của AIOps

---

## 7. Khuyến nghị Chi phí cho Sản xuất (Production Cost Recommendations)

Sau khi hoàn thành capstone 2 tuần và có baseline thực tế, các khuyến nghị sau đây nên được xem xét cho triển khai production dài hạn:

| Khuyến nghị | Thời điểm áp dụng | Tiết kiệm ước tính | Điều kiện |
|---|---|---|---|
| **Compute Savings Plans** | Sau 3 tháng baseline | 20-30% trên các nút on-demand ổn định | Chỉ dành cho các dịch vụ `ai-engine-api`, explainer, ingress, giám sát và core CDO dễ dự đoán. |
| **S3 Intelligent-Tiering** | Ngay lập tức | 10-15% storage cost | Thay thế manual lifecycle rules |
| **DynamoDB Reserved Capacity** | Sau 6 tháng baseline | 40-60% DDB cost | Khi provisioned rẻ hơn on-demand |
| **VPC Endpoint consolidation** | Khi có multi-workload | 50% endpoint cost | Dùng chung endpoints giữa nhiều platform |
| **CloudWatch Logs export to S3** | Ngay lập tức | 70% log storage cost | Logs >14 ngày export sang S3 IA |
| **Cross-region replication** | Chỉ khi yêu cầu DR | Tránh 2× storage cost | Không enable nếu không cần thiết |
| **QuickSight Enterprise** | Khi có >10 Finance users | Giảm per-user cost | $18/user/tháng vs $5 Reader |
| **Athena query result caching** | Ngay lập tức | 30-50% repeat query cost | Dashboard refresh dùng cache 24h |
| **KMS key consolidation** | Khi có compliance sign-off | 33% KMS cost | Dùng 1 CMK cho data + audit thay vì 3 keys |
| **Spot diversification** | Khi batch workload hoạt động | 20-50% độ ổn định chi phí worker | Sử dụng nhiều instance families và AZ cho công suất `ai-engine-worker`. |
| **Karpenter consolidation** | Sau khi biết mô hình workload | 15-40% chi phí EKS worker | Hợp nhất các nút chưa sử dụng hết và hết hạn các công suất nhàn rỗi một cách an toàn. |
| **Image retention policy** | Ngay lập tức | 10-30% ECR storage | Giữ lịch sử release bắt buộc nhưng xóa các image build không được tham chiếu. |

**Tổng tiết kiệm ước tính khi áp dụng tất cả các khuyến nghị**: `Cần bằng chứng: baseline đo lường dài hạn`. Các khu vực tiết kiệm có khả năng lớn nhất là định cỡ phù hợp nút on-demand, lên lịch trình worker spot, lưu giữ logs, Athena partition pruning và chia sẻ endpoint.

---

## 8. Phân tích Rủi ro Chi phí (Cost Risk Analysis)

| Rủi ro Chi phí | Tác động | Xác suất | Biện pháp Giảm thiểu |
|---|---|---|---|
| **Athena query storm** (ad-hoc queries không tối ưu) | +$50-200/ngày | Trung bình | Query result caching, partition pruning bắt buộc, query cost alarm |
| **S3 storage explosion** (không có lifecycle) | +$10-50/tháng | Thấp | Lifecycle rules tự động, bucket quota, storage growth alarm |
| **Lambda timeout loop** (retry storm) | +$20-100/ngày | Thấp | Circuit breaker, exponential backoff, max retry limit |
| **VPC endpoint always-on cost** | $28.80/tháng cố định | Chắc chắn | Không thể giảm; chấp nhận trade-off security vs cost |
| **AI Engine outage → CDO retry storm** | +$10-50/ngày | Trung bình | Circuit breaker với backoff, max retry 3 lần, fail-closed workflow |
| **CloudWatch Logs retention không giới hạn** | +$5-20/tháng | Thấp | Auto-expire 14 ngày, critical logs export S3 |
| **EKS baseline oversized** | +$100-500/tháng | Trung bình | Định cỡ phù hợp nhóm nút on-demand, xem xét requests/limits, sử dụng autoscaling. |
| **Spot worker runaway** | +$50-300/ngày | Trung bình | Giới hạn số nút worker tối đa, job TTL, giới hạn checkpoint/retry, tag chi phí của AIOps. |
| **Container Insights custom labels** | +$20-200/tháng | Trung bình | Giới hạn custom labels, kiểm soát khoảng thời gian cào metric, chính sách lưu giữ. |
| **Internal load balancer idle cost** | Chi phí cố định tháng | Chắc chắn | Chia sẻ endpoint khi an toàn, tránh ALB công cộng, đo lường LCU/NLCU. |
| **Mơ hồ sở hữu chi phí AIOps/CDO** | Tranh chấp ngân sách | Trung bình | Gắn tag riêng chi phí thời gian chạy AI khỏi chi phí phát triển/huấn luyện mô hình của AIOps. |

---

## 9. Câu hỏi Mở (Open Questions)

- [ ] **Q1**: Loại thực thể on-demand của EKS và số lượng nút tối thiểu nào được phê duyệt cho `ai-engine-api`, `ai-engine-explainer`, ingress, giám sát và các dịch vụ core CDO?
- [ ] **Q2**: Số giờ chạy nút worker spot tối đa/ngày mà AIOps có thể tiêu thụ trên cụm EKS do CDO host trong thời gian capstone là bao nhiêu?
- [ ] **Q3**: Tag scheme nào tách biệt baseline nền tảng CDO, lượt chạy CDO adapter, thời gian chạy AI được host và chi phí phát triển mô hình của AIOps?
- [ ] **Q4**: Ngân sách capstone nào sẽ thay thế cho giả định chỉ serverless $50-100 trước đây khi mà EKS hosting đã nằm trong phạm vi?
- [ ] **Q5**: Bao nhiêu người dùng Finance cần truy cập QuickSight trong quá trình demo và đánh giá độ sẵn sàng sản xuất?
- [ ] **Q6**: Những chi phí đo lường nào bắt buộc phải có cho bài thuyết trình cuối cùng: thực tế 14 ngày, thực tế mỗi lần chạy, thực tế mỗi tài khoản hay chi phí cho mỗi quyết định đúng?

---

## Tài liệu Liên quan (Related Documents)

- [`01_requirements_analysis_vi.md`](01_requirements_analysis_vi.md) - Yêu cầu hard về precision/FP và constraint về cadence/data source ảnh hưởng chi phí.
- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Kiến trúc lakehouse-centric và EKS hosting quyết định cost model compute/storage/network.
- [`03_security_design_vi.md`](03_security_design_vi.md) - VPC Endpoints, KMS CMKs, CloudTrail là các cost driver bảo mật.
- [`04_deployment_design_vi.md`](04_deployment_design_vi.md) - Chi phí pipeline CI/CD (GitHub Actions, CodeDeploy), chi phí observability stack.
- [`07_test_eval_report_vi.md`](07_test_eval_report_vi.md) - Bằng chứng kiểm thử tương lai sẽ xác thực các giả định chi phí trong phần 5 của tài liệu này.

---

**Phê duyệt**: Tài liệu này cần được review bởi mentor, Finance stakeholder, CDO platform owner và đại diện AIOps trước khi commit baseline cost model cho demo W12 T5.
