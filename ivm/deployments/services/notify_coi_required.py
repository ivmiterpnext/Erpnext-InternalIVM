import frappe

def send_notification(deployment, method=None):
    if deployment.coi_required and str(deployment.coi_required).lower() in ("yes", "1", "true"):  #TODO: figure out what type this field is
        deployment_url = f"{frappe.utils.get_url()}/app/project/{deployment.name}"

        frappe.sendmail(
            recipients=["test@example.com"],
            subject=f"COI Required on Deployment: {deployment.name}",
            message=f"COI Required on Deployment: {deployment.name}: <a href=\"{deployment_url}\">{deployment.name}</a>",
        )
