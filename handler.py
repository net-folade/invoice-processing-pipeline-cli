import os
import boto3
from urllib.parse import unquote_plus
from datetime import datetime, UTC
from decimal import Decimal
from botocore.exceptions import ClientError

table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
textract = boto3.client('textract')
sns = boto3.client('sns')
TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
supported_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff'}

PERMANENT_TEXTRACT_ERRORS = (
    'UnsupportedDocumentException',
    'InvalidParameterException',
    'DocumentTooLargeException',
    'BadDocumentException',
)

def lambda_handler(event, context):
    record = event['Records'][0]['s3']
    bucket = record['bucket']['name']
    key = unquote_plus(record['object']['key'])

    extension = os.path.splitext(key)[1].lower()

    if extension not in supported_extensions:
        print(f"File type {extension} not supported for key {key}.")
        return {'statusCode': 200, 'body': 'File type not supported'}

    invoice_id = key.removeprefix('uploads/').removesuffix(extension)
    processed_at = datetime.now(UTC).isoformat()

    try:
        response = textract.analyze_expense(
            Document={"S3Object": {'Bucket': bucket, 'Name': key}}
        )
    except ClientError as e:
        code = e.response['Error']['Code']
        print(f"Error calling Textract for key {key}: {code}")

        if code in PERMANENT_TEXTRACT_ERRORS:
            table.put_item(Item={
                'invoice_id': invoice_id,
                'processed_at': processed_at,
                's3_key': key,
                'status': 'TEXTRACT_REJECTED',
                'error_code': code,
            })
            notify(
                'Invoice processing failed',
                f'Invoice {invoice_id} could not be read by Textract ({code}).'
            )
            return {'statusCode': 200, 'body': 'Textract rejected the document'}
        raise

    documents = response.get('ExpenseDocuments', [])
    summary_fields = {}
    line_items = []
    if documents:
        summary_fields = extract_summary_fields(documents[0])
        line_items = extract_line_items(documents[0])

    status = 'PROCESSED' if summary_fields else 'NO_FIELDS_EXTRACTED'

    table.put_item(Item={
        'invoice_id': invoice_id,
        'processed_at': processed_at,
        's3_key': key,
        'status': status,
        'summary_fields': summary_fields,
        'line_items': line_items,
        'line_item_count': len(line_items),
    })

    print(f'{invoice_id}: {status}, {len(summary_fields)} summary fields, '
          f'{len(line_items)} line items extracted.')
    notify(
        'Invoice processing completed',
        f'Invoice {invoice_id} processed with status {status}.'
    )
    return {'statusCode': 200, 'body': 'Invoice processed successfully'}


def parse_field(field):
    # flatten one analyze_expense field into a label and a value dict
    label = field.get('Type', {}).get('Text', 'OTHER')
    value_detection = field.get('ValueDetection', {})

    return label, {
        'value': value_detection.get('Text'),
        'confidence': Decimal(str(value_detection.get('Confidence', 0))),
    }


def extract_summary_fields(expense_doc):
    # build a dictionary keyed on Textract's normalized labels
    summary = {}
    for field in expense_doc.get('SummaryFields', []):
        label, parsed = parse_field(field)
        if label == 'OTHER' or parsed['value'] is None:
            continue
        summary[label] = parsed
    return summary


def extract_line_items(expense_doc):
    # build a list of line items, each a dict of normalized labels
    line_items = []
    for group in expense_doc.get('LineItemGroups', []):
        for line_item in group.get('LineItems', []):
            parsed_item = {}
            for field in line_item.get('LineItemExpenseFields', []):
                label, parsed = parse_field(field)
                if label == 'OTHER' or parsed['value'] is None:
                    continue
                parsed_item[label] = parsed
            if parsed_item:
                line_items.append(parsed_item)
    return line_items


def notify(subject, message):
    sns.publish(TopicArn=TOPIC_ARN, Subject=subject, Message=message)