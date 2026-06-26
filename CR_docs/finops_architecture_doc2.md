# FinOps Watch - Architecture Improvement Proposal (Document 2)

**Document Type:** Architecture Review & Improvement Proposal
**Related Document:** Infrastructure Architecture Design (Document 2)
**Status:** Proposed Improvements
**Review Date:** W12

---

# Mục tiêu

Tài liệu này tổng hợp các đề xuất cải tiến kiến trúc nhằm:

* Tăng tính thực tiễn của hệ thống FinOps Watch.
* Giảm độ phức tạp vận hành (Operational Complexity).
* Tăng khả năng bảo vệ thiết kế (Architecture Defense).
* Tăng mức độ tuân thủ yêu cầu của Client.
* Tăng độ an toàn cho các Containment Actions.

---

# Priority 1 - Critical Improvements

## 1. Thay thế Amazon EKS bằng Amazon ECS Fargate

### Hiện trạng

```text
AI Container
↓
Amazon EKS
↓
Application Load Balancer
```

### Đề xuất

```text
AI Container
↓
Amazon ECS Fargate
↓
Internal Application Load Balancer
```

### Lý do

FinOps Watch hiện tại chỉ cần host AI Engine được cung cấp bởi đội AIOps dưới dạng containerized API.

Hệ thống không có yêu cầu:

* GPU Workloads
* Online Training
* Continuous Retraining
* Multi-Model Serving
* Kubernetes-Specific Features

### Lợi ích

* Đơn giản hơn trong vận hành.
* Giảm Operational Overhead.
* Không cần quản lý Kubernetes Cluster.
* Không phát sinh chi phí EKS Control Plane.
* Dễ triển khai và bảo trì.
* Phù hợp hơn với phạm vi của Capstone.

### Trade-off

* Giảm khả năng mở rộng sang các AI Workloads phức tạp trong tương lai.
* Không tận dụng được Kubernetes Ecosystem.

---

## 2. Bổ sung Containment Approval Flow

### Vấn đề hiện tại

Kiến trúc hiện tại chưa thể hiện rõ ai là người phê duyệt trước khi thực hiện Containment Action.

### Đề xuất

```text
AI Detection
↓
Containment Decision
↓
Approval Required?
├── YES
│   ↓
│ Finance / Engineering Approval
│   ↓
│ Execute
│
└── NO
    ↓
    Execute

↓
Audit Logging
```

### Lợi ích

* Đảm bảo Governance.
* Giảm rủi ro Containment sai.
* Tăng khả năng Audit và Compliance.
* Dễ trả lời các câu hỏi từ Mentor về Approval Process.

---

## 3. Bổ sung Production Safety Gate

### Vấn đề hiện tại

Kiến trúc chưa thể hiện rõ cách ngăn chặn hành động tự động trên Production Environment.

### Đề xuất

```text
Containment Request
↓
Environment Validation
↓
Production?
├── YES
│   ↓
│ Dry Run Only
│
└── NO
    ↓
    Containment Allowed
```

### Nguyên tắc

* NEVER Terminate Production Resources.
* NEVER Delete Data.
* NEVER Modify IAM.
* Production chỉ được phép:

  * Suggest
  * Tag
  * Dry Run

### Lợi ích

* Đáp ứng Hard Requirement của Client.
* Tăng độ an toàn hệ thống.
* Dễ chứng minh Guardrails trong Demo.

---

# Priority 2 - High Value Improvements

## 4. Theo dõi chi phí của chính hệ thống FinOps Watch

### Nguyên tắc

> Who watches the watcher?

FinOps Watch phải tự theo dõi chi phí vận hành của chính nó.

### Đề xuất

```text
AWS Budgets
↓
CDO Platform Cost Monitoring
↓
Alert
```

### Theo dõi

* Athena Cost
* ECS Fargate Cost
* QuickSight Cost
* S3 Storage Cost
* Data Scan Cost

### Lợi ích

* Đúng tinh thần FinOps.
* Tránh hệ thống giám sát chi phí lại trở thành nguồn phát sinh chi phí lớn.

---

## 5. Bổ sung Run Metadata Table

### Vấn đề hiện tại

Audit Trail đã có nhưng chưa theo dõi lịch sử thực thi Workflow.

### Đề xuất

Tạo bảng Run History.

| Run ID | Status  |
| ------ | ------- |
| 001    | SUCCESS |
| 002    | FAILED  |
| 003    | SKIPPED |

### Thông tin lưu trữ

* Run ID
* Execution Time
* Start Timestamp
* End Timestamp
* Records Processed
* Anomalies Found
* Alerts Sent
* Containments Triggered
* Failure Reason

### Lợi ích

* Hữu ích khi Demo.
* Hỗ trợ Troubleshooting.
* Hỗ trợ Monitoring và Reporting.

---

## 6. Bổ sung Confidence Threshold Logic

### Vấn đề hiện tại

AI trả về Confidence Score nhưng chưa có Business Decision Logic.

### Đề xuất

```text
Confidence >= 0.90
↓
Containment Candidate

Confidence 0.70 - 0.89
↓
Alert Only

Confidence < 0.70
↓
Log Only
```

### Lợi ích

* Giảm False Positive.
* Tăng độ minh bạch trong Decision Making.
* Dễ giải thích với Finance Team.

---

# Priority 3 - Architecture Maturity Improvements

## 7. Bổ sung Data Freshness Validation

### Vấn đề hiện tại

Workflow chưa kiểm tra tính đầy đủ của CUR Data.

### Đề xuất

```text
Workflow Start
↓
Check CUR Freshness
↓
CUR Complete?
├── NO
│   ↓
│ Skip Run
│   ↓
│ Engineering Alert
│
└── YES
    ↓
    Continue Processing
```

### Lợi ích

* Tránh Detection trên dữ liệu chưa hoàn chỉnh.
* Giảm False Positive.
* Tăng độ tin cậy của hệ thống.

---

## 8. Bổ sung Idempotency Design

### Requirement

Client yêu cầu tránh xử lý trùng lặp cùng một Cost Period.

### Đề xuất

```text
Run Key
=
Date + Account + Cost Period
```

Ví dụ:

```text
2026-06-23-dev-account-daily
```

### Lợi ích

* Ngăn double-processing.
* Tránh duplicate alerts.
* Tránh duplicate containment actions.

---

## 9. Bổ sung Rollback Flow

### Đề xuất

```text
Containment Action
↓
Execution
↓
Validation
↓
Issue Detected?
├── YES
│   ↓
│ Rollback
│   ↓
│ Restore Previous State
│
└── NO
    ↓
    Complete
```

### Lợi ích

* Tăng độ an toàn hệ thống.
* Đáp ứng yêu cầu Audit Trail.
* Hỗ trợ Incident Recovery.

---

# Priority 4 - Solution Architect Improvements

## 10. Tách riêng các nhóm dữ liệu

### Operational Data

#### Nội dung

* Workflow State
* Run Status
* Scheduler Metadata

#### Storage

```text
Amazon DynamoDB
```

---

### Cost Data

#### Nội dung

* CUR
* Cost Explorer Data
* Cost Aggregation Results

#### Storage

```text
Amazon S3
Amazon Athena
```

---

### Audit Data

#### Nội dung

* Alert History
* Approval Logs
* Containment Actions
* Rollback Events

#### Storage

```text
Amazon S3 Audit Bucket
```

---

## Kết luận

Ưu tiên triển khai theo thứ tự:

1. Chuyển Amazon EKS → Amazon ECS Fargate.
2. Bổ sung Containment Approval Flow.
3. Bổ sung Production Safety Gate.
4. Bổ sung Confidence Threshold Logic.
5. Bổ sung Data Freshness Validation.

Các cải tiến trên giúp hệ thống FinOps Watch:

* Đơn giản hơn.
* Chi phí thấp hơn.
* An toàn hơn.
* Dễ vận hành hơn.
* Dễ bảo vệ kiến trúc hơn trong quá trình Review và Defense.
