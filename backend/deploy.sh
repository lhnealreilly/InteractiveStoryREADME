#!/bin/bash

# Interactive Adventure Backend Deployment Script
# This script sets up and deploys the Lambda backend for the GitHub README adventure

echo "🎮 Setting up Interactive Adventure Backend..."

# Check prerequisites
command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI is required but not installed. Aborting." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed. Aborting." >&2; exit 1; }

# Configuration
FUNCTION_NAME="interactive-adventure"
REGION="us-east-1"
RUNTIME="python3.10"

echo "📋 Configuration:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Region: $REGION"
echo "   Runtime: $RUNTIME"

# Create deployment package
echo "📦 Creating deployment package..."
mkdir -p deployment
cd deployment

# Copy Lambda function
cp ../lambda_function.py .

# Install dependencies
echo "🔧 Installing Python dependencies..."
pip3.10 install --target . boto3 google-genai python-dotenv jinja2

# Copy .env file for environment variables
cp ../.env .

# Create fonts directory for better text rendering
mkdir -p fonts
echo "💾 Note: Add TTF font files to fonts/ directory for better text rendering"

# Package everything
echo "📦 Creating deployment ZIP..."
zip -r ../adventure-backend.zip . -x "*.pyc" "__pycache__/*"
cd ..

# Deploy with AWS CLI
echo "🚀 Deploying Lambda function..."

# Create execution role if it doesn't exist
ROLE_NAME="interactive-adventure-role"
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}'

echo "🔐 Creating IAM role..."
aws iam create-role \
  --role-name $ROLE_NAME \
  --assume-role-policy-document "$TRUST_POLICY" \
  --region $REGION 2>/dev/null || echo "Role may already exist"

# Attach policies
aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --region $REGION

# Create DynamoDB policy
DYNAMODB_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:'$REGION':*:table/adventure-game-state",
        "arn:aws:dynamodb:'$REGION':*:table/adventure-stats",
        "arn:aws:dynamodb:'$REGION':*:table/adventure-story-scenes"
      ]
    }
  ]
}'

aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name DynamoDBAccess \
  --policy-document "$DYNAMODB_POLICY" \
  --region $REGION

# Get account ID for ARN
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"

echo "⏳ Waiting for role propagation..."
sleep 10

# Create Lambda function
echo "🚀 Creating Lambda function..."
aws lambda create-function \
  --function-name $FUNCTION_NAME \
  --runtime $RUNTIME \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://adventure-backend.zip \
  --timeout 30 \
  --memory-size 512 \
  --layers "arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p310-Pillow:12",\
    "arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p310-pydantic:20",\
    "arn:aws:lambda:us-east-1:347599033421:layer:wkhtmltopdf-0_12_6:1" \
  --region $REGION 2>/dev/null || {
    echo "📝 Function exists, updating code..."
    aws lambda update-function-code \
      --function-name $FUNCTION_NAME \
      --zip-file fileb://adventure-backend.zip \
      --region $REGION
    
    echo "🔄 Updating function configuration with Pillow layer..."
    aws lambda update-function-configuration \
      --function-name $FUNCTION_NAME \
      --layers "arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p310-Pillow:12",\
        "arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p310-pydantic:20",\
        "arn:aws:lambda:us-east-1:347599033421:layer:wkhtmltopdf-0_12_6:1" \
      --region $REGION
  }

# Create DynamoDB tables
echo "🗄️  Creating DynamoDB tables..."

aws dynamodb create-table \
  --table-name adventure-game-state \
  --attribute-definitions AttributeName=game_id,AttributeType=S \
  --key-schema AttributeName=game_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION 2>/dev/null || echo "Table adventure-game-state may already exist"

aws dynamodb create-table \
  --table-name adventure-stats \
  --attribute-definitions AttributeName=stat_type,AttributeType=S \
  --key-schema AttributeName=stat_type,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION 2>/dev/null || echo "Table adventure-stats may already exist"

aws dynamodb create-table \
  --table-name adventure-story-scenes \
  --attribute-definitions AttributeName=scene_id,AttributeType=S \
  --key-schema AttributeName=scene_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION 2>/dev/null || echo "Table adventure-story-scenes may already exist"

# Create API Gateway
echo "🌐 Setting up API Gateway..."

# Check if API Gateway already exists
echo "🔍 Checking for existing API Gateway..."
API_ID=$(aws apigateway get-rest-apis \
  --query 'items[?name==`interactive-adventure-api`].id | [0]' \
  --output text --region $REGION)

if [ -z "$API_ID" ] || [ "$API_ID" = "None" ] || [ "$API_ID" = "null" ]; then
  echo "🆕 Creating new API Gateway..."
  API_ID=$(aws apigateway create-rest-api \
    --name "interactive-adventure-api" \
    --region $REGION \
    --query 'id' --output text)
else
  echo "✅ Found existing API Gateway with ID: $API_ID"
fi

echo "📡 API ID: $API_ID"

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources \
  --rest-api-id $API_ID \
  --region $REGION \
  --query 'items[?path==`/`].id' --output text)

# Check if proxy resource already exists
echo "🔍 Checking for existing proxy resource..."
RESOURCE_ID=$(aws apigateway get-resources \
  --rest-api-id $API_ID \
  --region $REGION \
  --query 'items[?pathPart==`{proxy+}`].id | [0]' --output text)

if [ -z "$RESOURCE_ID" ] || [ "$RESOURCE_ID" = "None" ] || [ "$RESOURCE_ID" = "null" ]; then
  echo "🆕 Creating proxy resource..."
  RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id $API_ID \
    --parent-id $ROOT_ID \
    --path-part '{proxy+}' \
    --region $REGION \
    --query 'id' --output text)
else
  echo "✅ Found existing proxy resource with ID: $RESOURCE_ID"
fi

# Create method
aws apigateway put-method \
  --rest-api-id $API_ID \
  --resource-id $RESOURCE_ID \
  --http-method ANY \
  --authorization-type NONE \
  --region $REGION 2>/dev/null || echo "Method may already exist"

# Set integration
FUNCTION_ARN="arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$FUNCTION_NAME"

aws apigateway put-integration \
  --rest-api-id $API_ID \
  --resource-id $RESOURCE_ID \
  --http-method ANY \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$FUNCTION_ARN/invocations" \
  --region $REGION 2>/dev/null || echo "Integration may already exist"

# Give API Gateway permission to invoke Lambda
aws lambda add-permission \
  --function-name $FUNCTION_NAME \
  --statement-id api-gateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*" \
  --region $REGION 2>/dev/null || echo "Permission may already exist"

# Configure binary media types for PNG images
echo "🖼️  Configuring binary media types..."
aws apigateway update-rest-api \
  --rest-api-id $API_ID \
  --patch-operations "op=add,path=/binaryMediaTypes/*~1*" \
  --region $REGION 2>/dev/null || echo "Binary media type may already be set"

# Deploy the API
aws apigateway create-deployment \
  --rest-api-id $API_ID \
  --stage-name prod \
  --region $REGION >/dev/null 2>&1

# Get the API endpoint
API_ENDPOINT="https://$API_ID.execute-api.$REGION.amazonaws.com/prod"

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "🎯 Your Adventure API Endpoint:"
echo "   $API_ENDPOINT"
echo ""
echo "🔧 Update your README.md with these URLs:"
echo "   Scene Image: $API_ENDPOINT/scene.png"
echo "   Choice A: $API_ENDPOINT/option/a.png"
echo "   Choice B: $API_ENDPOINT/option/b.png"
echo "   Choice A Link: $API_ENDPOINT/choice/a"
echo "   Choice B Link: $API_ENDPOINT/choice/b"
echo "   Stats: $API_ENDPOINT/stats.png"
echo "   History: $API_ENDPOINT/history.png"
echo ""

# Test the deployment
echo "🧪 Testing deployment..."
curl -s "$API_ENDPOINT/scene.png" > test_scene.png
if [ -s test_scene.png ]; then
    echo "✅ API is responding correctly!"
    rm test_scene.png
else
    echo "⚠️  API test failed. Check CloudWatch logs for errors."
fi

# Initialize game state
echo "🎮 Initializing game state..."
python3 -c "
import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='$REGION')
table = dynamodb.Table('adventure-game-state')

initial_state = {
    'game_id': 'global',
    'current_scene': 'start',
    'total_players': 0,
    'choices_made': 0,
    'last_updated': datetime.now().isoformat()
}

try:
    table.put_item(Item=initial_state)
    print('✅ Game state initialized')
except Exception as e:
    print(f'⚠️  Error initializing game state: {e}')
"

echo ""
echo "🎊 All done! Your interactive adventure backend is live!"
echo ""
echo "📖 Next steps:"
echo "1. Copy the API endpoint URLs above"
echo "2. Update your README.md with these URLs"
echo "3. Push to GitHub and watch the magic happen!"
echo ""
echo "🔍 Monitoring:"
echo "   CloudWatch Logs: aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo "   DynamoDB Console: https://console.aws.amazon.com/dynamodb/home?region=$REGION"
echo ""

# Clean up
rm -rf deployment
rm adventure-backend.zip

echo "🧹 Cleanup complete!"