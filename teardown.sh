#!/usr/bin/env bash
set -uo pipefail

REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

BUCKET=s3-invoice-processing-pipeline-1tg0t
TABLE=invoice-data
FUNCTION=invoice-pipeline-processor
ROLE=invoice-pipeline-lambda-role
POLICY=invoice-pipeline-permissions
TOPIC_ARN=arn:aws:sns:${REGION}:${ACCOUNT}:invoice-processing-topic
LOG_GROUP=/aws/lambda/${FUNCTION}

echo "Tearing down invoice pipeline in ${ACCOUNT}/${REGION}"

# 1. Remove the S3 event notification so nothing fires mid-teardown.
aws s3api put-bucket-notification-configuration \
  --bucket "${BUCKET}" \
  --notification-configuration '{}' || true

# 2. Delete the Lambda. This removes its resource-based policy with it.
aws lambda delete-function --function-name "${FUNCTION}" || true

# 3. Delete the log group. Not removed with the function.
aws logs delete-log-group --log-group-name "${LOG_GROUP}" || true

# 4. Delete the SNS topic. Subscriptions go with it.
aws sns delete-topic --topic-arn "${TOPIC_ARN}" || true

# 5. Delete the DynamoDB table.
aws dynamodb delete-table --table-name "${TABLE}" || true

# 6. Empty the versioned bucket: current versions, noncurrent versions,
#    and delete markers. A versioned bucket will not delete while any
#    of the three remain.
echo "Emptying ${BUCKET}"
while true; do
  VERSIONS=$(aws s3api list-object-versions \
    --bucket "${BUCKET}" \
    --max-keys 500 \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
    --output json 2>/dev/null)

  if [ -z "${VERSIONS}" ] || [ "$(echo "${VERSIONS}" | grep -c '"Key"')" -eq 0 ]; then
    break
  fi

  aws s3api delete-objects --bucket "${BUCKET}" --delete "${VERSIONS}" >/dev/null
done

while true; do
  MARKERS=$(aws s3api list-object-versions \
    --bucket "${BUCKET}" \
    --max-keys 500 \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
    --output json 2>/dev/null)

  if [ -z "${MARKERS}" ] || [ "$(echo "${MARKERS}" | grep -c '"Key"')" -eq 0 ]; then
    break
  fi

  aws s3api delete-objects --bucket "${BUCKET}" --delete "${MARKERS}" >/dev/null
done

aws s3api delete-bucket --bucket "${BUCKET}" --region "${REGION}" || true

# 7. Delete the inline policy, then the role. The role cannot be deleted
#    while any policy is still attached.
aws iam delete-role-policy --role-name "${ROLE}" --policy-name "${POLICY}" || true
aws iam delete-role --role-name "${ROLE}" || true

echo "Teardown complete. Verifying nothing remains:"
aws s3api head-bucket --bucket "${BUCKET}" 2>&1 | tail -1
aws dynamodb list-tables --query "TableNames[?@=='${TABLE}']" --output text
aws lambda list-functions --query "Functions[?FunctionName=='${FUNCTION}'].FunctionName" --output text
aws sns list-topics --query "Topics[?contains(TopicArn,'invoice-processing-topic')].TopicArn" --output text
aws iam list-roles --query "Roles[?RoleName=='${ROLE}'].RoleName" --output text