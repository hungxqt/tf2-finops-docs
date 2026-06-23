# FinOps Watch - Deployment & CI/CD Design Improvements (Document 4)

**Document Type:** Deployment & CI/CD Review
**Related Document:** 04_deployment_design_vi.md
**Status:** Proposed Improvements
**Priority:** W12 Refinement

---

# Mục tiêu

Các cải tiến dưới đây nhằm:

* Đơn giản hóa Deployment Architecture.
* Giảm Operational Overhead.
* Đồng bộ với kiến trúc ECS Fargate.
* Tăng khả năng bảo vệ kiến trúc trong Mentor Defense.
* Bổ sung các yêu cầu còn thiếu trong đề bài.

---

# Priority 1 (Bắt buộc nên làm)

## 1. Chuyển từ EKS Deployment sang ECS Fargate Deployment

### Hiện tại

```text
AI Container
↓
EKS
↓
Helm
↓
ArgoCD
```

### Đề xuất

```text
AI Container
↓
Amazon ECS Fargate
↓
Internal Application Load Balancer
```

### Thay đổi tài liệu

### IaC Modules

Hiện tại:

```text
modules/
├─ eks/
```

Đề xuất:

```text
modules/
├─ ecs/
```

### Deployment

Hiện tại:

```text
Terraform
↓
ArgoCD
↓
EKS
```

Đề xuất:

```text
Terraform
↓
ECS Service Update
↓
Rolling Deployment
```

### Lợi ích

* Giảm độ phức tạp.
* Không cần Kubernetes Operations.
* Không cần ArgoCD.
* Không cần Helm.
* Không cần Karpenter.
* Chi phí thấp hơn.
* Dễ defend hơn.

---

## 2. Thêm Cost Gate trong CI/CD

### Vấn đề

Đây là dự án FinOps nhưng chưa kiểm soát chi phí deployment.

### Đề xuất

```text
Terraform Plan
↓
Cost Estimation
↓
Budget Validation
↓
Deploy
```

### Quy tắc

Nếu deployment:

* Tăng chi phí >20%

↓

```text
Manual Review Required
```

### Lợi ích

Mentor rất thích vì đúng tinh thần FinOps.

---

## 3. Thêm Data Freshness Validation

### Vấn đề

Hiện tại workflow chạy theo lịch.

Nhưng chưa kiểm tra:

```text
CUR đã sẵn sàng chưa?
```

### Đề xuất

```text
EventBridge
↓
Step Functions
↓
Check CUR Freshness
↓
Ready?
```

Nếu:

```text
NO
```

↓

```text
Skip Run
↓
Engineering Alert
```

Nếu:

```text
YES
```

↓

```text
Continue Workflow
```

### Lợi ích

Giảm false positive.

---

## 4. Thêm Run Metadata Table

### Vấn đề

Audit Trail đã có.

Nhưng chưa theo dõi lịch sử vận hành.

### Đề xuất

Lưu vào DynamoDB:

| Field                  |
| ---------------------- |
| Run ID                 |
| Status                 |
| Start Time             |
| End Time               |
| Records Processed      |
| Anomalies Found        |
| Alerts Sent            |
| Containments Triggered |

### Ví dụ

| Run ID | Status  |
| ------ | ------- |
| 001    | SUCCESS |
| 002    | FAILED  |
| 003    | SKIPPED |

### Lợi ích

Demo rất dễ.

---

# Priority 2 (Mentor rất thích)

## 5. Bổ sung Idempotency Design

### Vấn đề

Đề bài yêu cầu.

Nhưng tài liệu chưa mô tả chi tiết.

### Đề xuất

```text
Run Key
=
Account ID
+
Date
+
Period
```

Ví dụ:

```text
123456789012
+
2026-06-23
+
24H
```

Nếu tồn tại:

```text
SKIP EXECUTION
```

### Lợi ích

Tránh chạy trùng.

---

## 6. Bổ sung Auto Rollback Flow

### Hiện tại

Có rollback nhưng chưa có decision flow.

### Đề xuất

```text
Deployment Failed
↓
Health Check Failed
↓
Auto Rollback
↓
Previous Stable Version
```

### Lợi ích

Tăng Reliability.

---

## 7. Bổ sung Deployment Architecture Decision Record

### Quyết định

#### Chọn ECS Fargate

##### Lý do

* Managed Service.
* Ít vận hành.
* Chi phí thấp.
* Đúng scope FinOps Watch.

#### Không chọn EKS

##### Lý do

* Không cần Kubernetes Features.
* Không cần GPU Workloads.
* Không cần Complex Scheduling.
* Không cần Multi-Tenant AI Platform.

### Lợi ích

Rất hữu ích khi mentor hỏi:

> Tại sao không dùng EKS?

---

# Priority 3 (Điểm cộng Solution Architect)

## 8. Giảm Observability Stack

### Hiện tại

```text
CloudWatch
+
X-Ray
+
Prometheus
+
Grafana
+
Container Insights
```

### Đề xuất

```text
CloudWatch
+
X-Ray
```

### Lợi ích

* Đơn giản hơn.
* Rẻ hơn.
* Đủ cho Capstone.

---

## 9. Bổ sung Platform Cost Monitoring

### Nguyên tắc

> Who watches the watcher?

### Theo dõi

* ECS Fargate Cost
* Lambda Cost
* Athena Cost
* S3 Cost
* QuickSight Cost

### Luồng

```text
AWS Budgets
↓
Platform Cost Alert
↓
Finance Notification
```

### Lợi ích

Đúng tinh thần FinOps.

---

## 10. Bổ sung Deployment Promotion Flow

### Đề xuất

```text
Sandbox
↓
Staging
↓
Production
```

### Quy tắc

Không deploy trực tiếp Production.

Bắt buộc:

```text
Sandbox Validation
↓
Staging Validation
↓
Manual Approval
↓
Production
```

### Lợi ích

Tăng Governance.

---

# Kết luận

Ưu tiên triển khai theo thứ tự:

1. Chuyển EKS → ECS Fargate.
2. Thêm Cost Gate trong CI/CD.
3. Thêm Data Freshness Validation.
4. Thêm Run Metadata Table.
5. Thêm Idempotency Design.
6. Thêm Auto Rollback Flow.

Các cải tiến trên giúp Deployment & CI/CD Design tập trung đúng mục tiêu của FinOps Watch:

* Cost Efficiency
* Simplicity
* Auditability
* Reliability
* Governance

thay vì tập trung quá nhiều vào Kubernetes Platform Operations.
