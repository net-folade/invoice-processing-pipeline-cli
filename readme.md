# Invoice Processing Pipeline

> Event-driven pipeline that extracts structured invoice data from documents uploaded to S3 using Amazon Textract, stores the results in DynamoDB, and publishes processing notifications with Amazon SNS.

> **Companion repo:** This project extends the architecture from [s3-metadata-pipeline-cli](https://github.com/net-folade/s3-metadata-pipeline-cli) by replacing plain-text metadata extraction with Amazon Textract invoice processing. See the Terraform implementation: [invoice-processing-pipeline](https://github.com/net-folade/invoice-processing-pipeline).

### Architecture

`S3 (uploads/) → Lambda → Textract AnalyzeExpense → DynamoDB + SNS`

Objects uploaded to the `uploads/` prefix trigger a Lambda function, which validates the file type, extracts invoice data using Amazon Textract, stores the result in DynamoDB, and publishes a completion or failure notification to SNS.

### Features

- Processes invoices automatically on upload
- Extracts normalized invoice fields with confidence scores
- Stores invoice summary fields and line items in DynamoDB
- Publishes processing status through SNS
- Validates supported file types before invoking Textract
- Preserves every extraction run using a composite key

### Design Decisions & Tradeoffs

- **Synchronous `AnalyzeExpense` over `StartExpenseAnalysis`.** Single-page invoices complete within one Lambda invocation, avoiding additional infrastructure.
- **`AnalyzeExpense` over `AnalyzeDocument`.** Returns normalized invoice fields directly with lower cost and less post-processing.
- **Composite key (`invoice_id` + `processed_at`).** Preserves every extraction run instead of overwriting previous results.
- **One DynamoDB item per invoice.** Matches the access pattern of retrieving complete invoices with a single request.
- **SNS over SES.** Simple email notifications without managing verified identities.
- **Handler validation over S3 suffix filters.** Keeps validation logic in one place while supporting multiple file types.
- **Persist failed extractions.** Failed and empty extractions are stored with a status for troubleshooting.

### Tech Stack

`AWS CLI` `Amazon S3` `AWS Lambda` `Amazon Textract` `Amazon DynamoDB` `Amazon SNS` `IAM` `Python 3.12` `boto3`

### Prerequisites

- AWS CLI configured
- Python 3.12
- AWS account with permissions to create S3, Lambda, DynamoDB, SNS, and IAM resources
- Email address for the SNS subscription

### Deployment

Resources are created manually with the AWS CLI in dependency order.

See `commands.md` for the complete deployment commands.

Required configuration:

- `TABLE_NAME`
- `SNS_TOPIC_ARN`

Update the account ID, bucket name, and region in the policy files before deployment.

### Usage

Upload an invoice to the `uploads/` prefix:

```bash
aws s3 cp samples/invoice--1.pdf s3://<bucket-name>/uploads/invoice--1.pdf
```

Retrieve the processed result:

```bash
aws dynamodb get-item \
  --table-name invoice-data \
  --key '{"invoice_id":{"S":"invoice--1"},"processed_at":{"S":"<timestamp>"}}'
```

Example item:

```json
{
  "invoice_id": "invoice--1",
  "processed_at": "2026-08-06T14:02:11.418293+00:00",
  "status": "PROCESSED",
  "summary_fields": {
    "VENDOR_NAME": {
      "value": "Acme Supply Co",
      "confidence": 98.4
    },
    "TOTAL": {
      "value": "$1,240.00",
      "confidence": 99.2
    }
  },
  "line_items": [
    {
      "ITEM": {
        "value": "Widget, 10-pack",
        "confidence": 94.7
      }
    }
  ]
}
```

### Cost Considerations

Amazon Textract is the primary cost driver. S3, Lambda, DynamoDB on-demand, and SNS remain inexpensive for low-volume workloads.

### Tested / Not Covered

**Verified**

- End-to-end extraction of single-page PDF invoices
- Unsupported file types rejected before invoking Textract
- Failed Textract requests recorded with an appropriate status
- Re-uploading the same invoice creates a new extraction record

**Not Covered**

- Multi-page invoice processing
- Dead-letter queue for failed invocations
- Automated unit and integration tests
- Processing multiple S3 event records in one invocation

### Monitoring

CloudWatch Logs capture extraction status and errors. No alarms or metric filters are configured.

### Security

- Least-privilege IAM permissions
- Lambda invocation restricted to the source bucket and account
- `textract:AnalyzeExpense` requires `*` because resource-level permissions are unsupported
- No application secrets required

### Future Improvements

- Terraform implementation
- Asynchronous Textract for multi-page documents
- Dead-letter queue and CloudWatch alarms
- Process every S3 event record
- Confidence thresholding for manual review