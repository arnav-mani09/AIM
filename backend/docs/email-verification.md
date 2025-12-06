# Email verification plan

1. Extend the `user` table with columns:
   - `is_verified` (bool)
   - `verification_token` (string, nullable)
   - `verification_sent_at` (timestamp)

2. Generate a random token on registration; send email via provider (SendGrid/SES).

3. Add `/api/v1/auth/verify` endpoint that accepts the token, flips `is_verified`, clears the token.

4. Frontend: `/auth/verify` page that reads `token` query param, calls the endpoint, and shows success/failure.
