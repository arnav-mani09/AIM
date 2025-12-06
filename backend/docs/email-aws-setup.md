# AWS SES Email Setup

1. Create an AWS account and verify a domain or sender email in SES.
2. Generate SMTP credentials or use AWS SDK credentials with SES.
3. Store credentials in `.env`:
   ```env
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=us-east-1
   EMAIL_FROM_ADDRESS=coach@yourdomain.com
   FRONTEND_BASE_URL=http://localhost:3000
   ```
