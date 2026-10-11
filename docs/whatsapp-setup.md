# Connecting the WhatsApp Business Cloud API

## 1. Create the Meta app

1. Go to <https://developers.facebook.com/apps> and click **Create app**. Choose **Business** (or "Other → Business").
2. Under **Add products**, choose **WhatsApp → Set up**, then select or create a Meta Business Account.
3. Open **WhatsApp → API Setup**. Meta gives you a free **test phone number** and a temporary access token.
   - Copy the **Phone number ID** into `WHATSAPP_PHONE_NUMBER_ID`.
   - Copy the **Temporary access token** into `WHATSAPP_TOKEN`. It expires in 24 hours; for production, see step 5.
   - Add your own phone under **To**, so the test number is allowed to message you.
4. Open **App settings → Basic** and copy the **App secret** into `WHATSAPP_APP_SECRET`.

## 2. Expose your server over HTTPS

Meta only calls HTTPS URLs. For local development:

```bash
pip install -r requirements.txt    
copy .env.example .env   
uvicorn app.main:app --port 8000
ngrok http 8000            # gives you https://<id>.ngrok-free.app
```

## 3. Register the webhook

1. Open **WhatsApp → Configuration → Webhook → Edit**.
2. Set **Callback URL** to `https://<your-host>/webhook`.
3. Set **Verify token** to the same value as `WHATSAPP_VERIFY_TOKEN` in `.env`.
4. Click **Verify and save**. Meta calls `GET /webhook` and the app echoes the challenge.
5. Under **Webhook fields**, **subscribe to `messages`**.

## 4. Test

Send "hi" from your phone to the test number. You should receive the language list.

Troubleshooting:

- **Verification fails:** the verify token doesn't match, or the server isn't reachable over HTTPS.
- **401 in the server logs:** `WHATSAPP_APP_SECRET` is wrong, so the signature check failed.
- **No reply, with `WhatsApp API error 401` in the logs:** the token expired.
- **Error `131030`:** the recipient isn't in the test number's allowed list.

## 5. Go live (for the client)

1. **Permanent token:** in Business Settings, go to **Users → System users**, add an admin system user, then
   **Generate token** for the app with the `whatsapp_business_messaging` and `whatsapp_business_management`
   permissions. Put that token in `WHATSAPP_TOKEN`.
2. **Real phone number:** in **WhatsApp → API Setup**, choose **Add phone number**. Use a number that isn't
   registered on the WhatsApp app, then verify it by SMS or a voice call.
3. **Business verification:** complete it in Business Settings. Without it, messaging limits stay low.
4. **Display name and profile:** set them in WhatsApp Manager. The display name needs approval.
5. **Payment method:** add one in WhatsApp Manager. Conversations that users start are billed under Meta's
   pricing.
6. Set `ENVIRONMENT=production`, use strong values for `ADMIN_PASSWORD` and `JWT_SECRET`, and configure SMTP.
