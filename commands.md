# Commands

## Setup
```bash
REGION=us-east-1
ACCOUNT=<account-id>

aws sts get-caller-identity
```

## IAM
```bash
aws iam create-role \
--role-name invoice-pipeline-lambda-role \
--assume-role-policy-document file://policies/trust.json

aws iam put-role-policy \
--role-name invoice-pipeline-lambda-role \
--policy-name invoice-pipeline-permissions \
--policy-document file://policies/permissions.json
```

## bucket
```bash
aws s3api create-bucket \
--bucket s3-invoice-processing-pipeline-1tg0t \
--region us-east-1

aws s3api put-bucket-versioning \
--bucket s3-invoice-processing-pipeline-1tg0t \
--versioning-configuration Status=Enabled

aws s3api put-bucket-lifecycle-configuration \
--bucket s3-invoice-processing-pipeline-1tg0t \
--lifecycle-configuration file://policies/lifecycle.json
```

## dynamodb
```bash
aws dynamodb create-table \
--table-name invoice-data \
--attribute-definitions AttributeName=invoice_id,AttributeType=S AttributeName=processed_at,AttributeType=S \
--key-schema AttributeName=invoice_id,KeyType=HASH AttributeName=processed_at,KeyType=RANGE \
--billing-mode PAY_PER_REQUEST
```

## sns
```bash
aws sns create-topic --name invoice-processing-topic

aws sns subscribe \
--topic-arn arn:aws:sns:us-east-1:<account-id>:invoice-processing-topic \
--protocol email \
--notification-endpoint you@example.com

aws sns list-subscriptions-by-topic \
--topic-arn arn:aws:sns:us-east-1:<account-id>:invoice-processing-topic
```

## lambda
```bash
cd lambda/
zip ../function.zip handler.py
cd ..

aws lambda create-function \
--function-name invoice-pipeline-processor \
--runtime python3.12 \
--role arn:aws:iam::<account-id>:role/invoice-pipeline-lambda-role \
--handler handler.lambda_handler \
--zip-file fileb://function.zip \
--environment "Variables={TABLE_NAME=invoice-data,SNS_TOPIC_ARN=arn:aws:sns:us-east-1:<account-id>:invoice-processing-topic}" \
--timeout 30
```

## Event wiring
```bash
aws lambda add-permission \
--function-name invoice-pipeline-processor \
--statement-id s3-invoke-lambda \
--action lambda:InvokeFunction \
--principal s3.amazonaws.com \
--source-arn arn:aws:s3:::s3-invoice-processing-pipeline-1tg0t \
--source-account <account-id>

aws s3api put-bucket-notification-configuration \
--bucket s3-invoice-processing-pipeline-1tg0t \
--notification-configuration file://policies/notification-config.json
```

## Verification
```bash
aws s3 cp samples/invoice.pdf s3://s3-invoice-processing-pipeline-1tg0t/uploads/invoice.pdf
aws s3 cp samples/notes.txt s3://s3-invoice-processing-pipeline-1tg0t/uploads/notes.txt
aws s3 cp samples/not-an-invoice.jpg s3://s3-invoice-processing-pipeline-1tg0t/uploads/not-an-invoice.jpg

aws dynamodb scan --table-name invoice-data

aws logs tail /aws/lambda/invoice-pipeline-processor --follow
```