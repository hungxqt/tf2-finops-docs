# FinOps Watch - Security Design Improvement Proposal (Document 3)

**Document Type:** Security Architecture Review
**Related Document:** 03_security_design_vi.md
**Status:** Proposed Improvements
**Priority:** W12 Refinement

---

# Mục tiêu

Các cải tiến dưới đây nhằm:

* Đơn giản hóa Security Architecture.
* Loại bỏ Over-Engineering do phụ thuộc Kubernetes.
* Tăng khả năng bảo vệ thiết kế trong Architecture Defense.
* Tăng tính tuân thủ yêu cầu Client.
* Tăng độ an toàn cho Containment Actions.
* Đồng bộ với kiến trúc Amazon ECS Fargate được đề xuất trong Document 2.

---

# Priority 1 - Critical Improvements

## 1. Chuyển từ EKS Security Model sang ECS Fargate Security Model

### Hiện trạng

Document hiện tại phụ thuộc nhiều vào:

* Kubernetes RBAC
* IAM Roles for Service Accounts (IRSA)
* Node Groups
* Pod Security Admission
* Network Policies
* Node Affinity
* Spot Isolation

### Đề xuất

Kiến trúc mới:

```text
AI Container
↓
Amazon ECS Fargate Service
↓
Internal Application Load Balancer
↓
AWS Services (qua VPC Endpoints)
```

### Security Components

| Component        | Security Control                  |
| ---------------- | --------------------------------- |
| ECS Task         | Task Role                         |
| ECS Runtime      | Execution Role                    |
| Secrets          | AWS Secrets Manager               |
| Network          | Private Subnets + Security Groups |
| Service Exposure | Internal ALB Only                 |

### Lợi ích

* Giảm đáng kể độ phức tạp.
* Không cần quản lý Kubernetes Security Stack.
* Giảm bề mặt tấn công (Attack Surface).
* Giảm chi phí vận hành.

---

## 2. Bổ sung Approval Security Model

### Vấn đề hiện tại

Document chưa mô tả rõ:

> Ai được quyền phê duyệt Containment Action?

### Đề xuất

```text
AI Detection
↓
Containment Candidate
↓
Approval Workflow
↓
Finance / Engineering Approver
↓
Execution
```

### Approval Matrix

| Containment Type                | Approver         |
| ------------------------------- | ---------------- |
| Tag for Review                  | Auto Approved    |
| Schedule Shutdown (Dev/Sandbox) | Engineering Lead |
| Scale Down Sandbox              | Engineering Lead |
| Production Action               | Not Allowed      |

### Audit Requirements

Bổ sung:

```json
{
  "approved_by": "engineering-lead",
  "approved_at": "2026-06-23T07:20:00Z"
}
```

### Lợi ích

* Tăng Governance.
* Giảm rủi ro Auto-Containment.
* Tăng khả năng Audit.

---

## 3. Bổ sung Production Safety Gate

### Vấn đề hiện tại

Document chưa mô tả rõ cơ chế bảo vệ Production.

### Đề xuất

```text
Containment Request
↓
Environment Validation
↓
Production?
```

Nếu:

```text
Production
```

↓

```text
Dry Run Only
```

Nếu:

```text
Dev / Sandbox
```

↓

```text
Containment Allowed
```

### Security Policy

Production chỉ được phép:

* Alert
* Suggest
* Tag
* Dry Run

Production tuyệt đối không được:

* Terminate Resource
* Delete Data
* Modify IAM
* Scale Down Automatically

### Lợi ích

* Đáp ứng Hard Requirement.
* Tăng mức độ tin cậy của hệ thống.

---

# Priority 2 - High Value Improvements

## 4. Bổ sung Data Classification Matrix

### Đề xuất

| Data Type         | Classification | Encryption Required |
| ----------------- | -------------- | ------------------- |
| Cost Data         | Internal       | Yes                 |
| Audit Logs        | Confidential   | Yes                 |
| Secrets           | Restricted     | Yes                 |
| Dashboard Metrics | Internal       | Yes                 |

### Lợi ích

* Thể hiện tư duy Information Security.
* Phù hợp với SOC 2 và ISO 27001.

---

## 5. Bổ sung Separation of Duties Matrix

### Đề xuất

| Activity               | CDO                   | AIOps             |
| ---------------------- | --------------------- | ----------------- |
| Deploy AI Container    | Owns                  | Provides Artifact |
| Modify Detection Logic |                       | Owns              |
| Execute Containment    | Owns                  |                   |
| Approve Containment    | Finance / Engineering |                   |
| Manage Secrets         | Owns                  |                   |

### Lợi ích

* Tránh quyền lực tập trung.
* Tăng khả năng Compliance.

---

## 6. Bổ sung Security Monitoring

### Đề xuất

```text
CloudTrail
↓
Security Monitoring
↓
Alert
```

### Theo dõi

* Failed AssumeRole
* Unauthorized Access
* Repeated Denied Actions
* Secrets Access Failures

### Lợi ích

* Tăng khả năng phát hiện Security Incidents.
* Hỗ trợ Audit.

---

# Priority 3 - Architecture Maturity Improvements

## 7. Bổ sung Incident Response Flow

### Đề xuất

```text
Security Event
↓
Detection
↓
Classification
↓
Containment
↓
Investigation
↓
Recovery
↓
Post Incident Review
```

### Ví dụ

* Secret Leak
* Unauthorized API Call
* Suspicious Containment Request

### Lợi ích

* Tăng tính hoàn chỉnh của Security Design.
* Mentor rất thích phần này.

---

## 8. Bổ sung Security Architecture Decision Record

### Quyết định

#### Chọn Amazon ECS Fargate

##### Vì sao

* Chi phí thấp hơn.
* Ít Operational Overhead.
* Phù hợp với Workload hiện tại.

##### Không chọn Amazon EKS

* Không cần Kubernetes Ecosystem.
* Không cần GPU Workloads.
* Không cần Complex Scheduling.
* Không cần Multi-Tenant AI Platform.

---

## 9. Bổ sung Containment Security Threshold

### Đề xuất

```text
Confidence >= 0.90
↓
Containment Candidate

0.70 - 0.89
↓
Alert Only

< 0.70
↓
Log Only
```

### Security Benefit

* Giảm False Positive.
* Giảm nguy cơ Containment nhầm.

---

# Priority 4 - FinOps Security Improvements

## 10. Security Cost Governance

### Nguyên tắc

> Who watches the watcher?

### Đề xuất

Theo dõi:

* CloudTrail Cost
* Secrets Manager Cost
* KMS Cost
* ECS Fargate Cost
* Athena Query Cost

### Alert Threshold

* 80% Budget → Warning
* 100% Budget → Critical Alert

### Lợi ích

* Đúng tinh thần FinOps.
* Tránh Security Controls tạo ra chi phí vượt kiểm soát.

---

# Kết luận

Ưu tiên triển khai theo thứ tự:

1. Chuyển EKS Security Model sang ECS Fargate Security Model.
2. Bổ sung Approval Security Model.
3. Bổ sung Production Safety Gate.
4. Bổ sung Data Classification Matrix.
5. Bổ sung Separation of Duties Matrix.

Các cải tiến trên sẽ giúp Security Design tập trung đúng vào mục tiêu của FinOps Watch:

* Least Privilege
* Auditability
* Safe Containment
* Governance
* Cost Efficiency

thay vì tập trung quá nhiều vào Kubernetes Platform Security.
