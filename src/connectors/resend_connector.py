import os
import logging
import resend

# Configure basic logging so you can see email success/failures in your console
logger = logging.getLogger(__name__)

# Initialize the API key once when the module loads.
# Make sure RESEND_API_KEY is set in your local .env and Render dashboard.
resend.api_key = os.environ.get("RESEND_API_KEY", "").strip()

def send_welcome_email(to_email: str, user_name: str) -> bool:
    """
    Sends a welcome email to a newly registered user.
    Returns True if successful, False otherwise.
    """

    html_content = f"""
        <div style="background-color: #1A1A1A; padding: 40px 20px; font-family: 'Geist', 'Helvetica Neue', Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #242424; border: 1px solid #404040; border-radius: 8px; padding: 32px; text-align: left;">
                
                <h2 style="margin-top: 0; color: #F2F2F2; font-size: 24px; font-weight: 600;">
                    Welcome aboard, {user_name}!
                </h2>
                
                <p style="color: #A6A6A6; font-size: 16px; line-height: 1.6; margin-bottom: 24px;">
                    We are thrilled to have you here. Your workspace is ready, and you can now start generating API keys and integrating our services.
                </p>
                
                <a href="https://your-frontend-url.com/dashboard" style="display: inline-block; background-color: #2EBA8E; color: #1A1A1A; font-weight: 600; font-size: 14px; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    Go to Dashboard
                </a>
                
                <hr style="border: 0; border-top: 1px solid #404040; margin: 32px 0;" />
                
                <p style="color: #A6A6A6; font-size: 14px; margin-bottom: 0;">
                    Cheers,<br/>
                    <strong style="color: #F2F2F2; font-weight: 500;">The API Team</strong>
                </p>
                
            </div>
        </div>
        """
    try:
        # Note: While using the free tier without a domain, 
        # 'from' MUST be onboarding@resend.dev
        # 'to_email' MUST be your verified email (matheuslcavini@usp.br)
        params = {
            "from": "onboarding@resend.dev",
            "to": to_email,
            "subject": f"Welcome to NexusAPI, {user_name}! 🚀",
            "html": html_content
        }
        
        # Fire the email via Resend
        response = resend.Emails.send(params)
        
        # Log success and return True
        logger.info(f"Welcome email sent successfully to {to_email}. Resend ID: {response.get('id')}")
        return True
        
    except Exception as e:
        # Catch any network or validation errors so the main registration flow doesn't crash
        logger.error(f"Failed to send welcome email to {to_email}. Error: {str(e)}")
        return False

def send_verification_email(to_email: str, user_name: str, magic_link: str) -> bool:
    """
    Sends a verification email with a magic link to a newly registered user.
    Returns True if successful, False otherwise.
    """

    html_content = f"""
        <div style="background-color: #1A1A1A; padding: 40px 20px; font-family: 'Geist', 'Helvetica Neue', Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #242424; border: 1px solid #404040; border-radius: 8px; padding: 32px; text-align: left;">
                
                <h2 style="margin-top: 0; color: #F2F2F2; font-size: 24px; font-weight: 600;">
                    Verify your email address
                </h2>
                
                <p style="color: #A6A6A6; font-size: 16px; line-height: 1.6; margin-bottom: 24px;">
                    Hi {user_name}, welcome to NexusAPI! To complete your registration and unlock your dashboard, please verify your email address.
                    <br><br>
                    <strong style="color: #F2F2F2;">Note:</strong> This link will expire in 15 minutes.
                </p>
                
                <a href="{magic_link}" style="display: inline-block; background-color: #2EBA8E; color: #1A1A1A; font-weight: 600; font-size: 14px; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-bottom: 24px;">
                    Verify Email
                </a>

                <p style="color: #737373; font-size: 13px; line-height: 1.5; margin-bottom: 0;">
                    If the button doesn't work, copy and paste this URL into your browser:<br>
                    <a href="{magic_link}" style="color: #2EBA8E; text-decoration: underline; word-break: break-all;">{magic_link}</a>
                </p>
                
                <hr style="border: 0; border-top: 1px solid #404040; margin: 32px 0;" />
                
                <p style="color: #A6A6A6; font-size: 14px; margin-bottom: 0;">
                    Cheers,<br/>
                    <strong style="color: #F2F2F2; font-weight: 500;">The API Team</strong>
                </p>
                
            </div>
        </div>
        """
    try:
        # Note: While using the free tier without a domain, 
        # 'from' MUST be onboarding@resend.dev
        # 'to_email' MUST be your verified email
        params = {
            "from": "onboarding@resend.dev",
            "to": to_email,
            "subject": "Verify your email for NexusAPI 🔒",
            "html": html_content
        }
        
        # Fire the email via Resend
        response = resend.Emails.send(params)
        
        # Log success and return True
        logger.info("Verification email sent successfully to %s. Resend ID: %s", to_email, response.get('id'))
        return True
        
    except Exception as e:
        # Catch any network or validation errors so the main registration flow doesn't crash
        logger.error("Failed to send verification email to %s. Error: %s", to_email, str(e))
        return False