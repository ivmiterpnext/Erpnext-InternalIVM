let issuetypes = {
    "IT": "IT",
    "Permission Change": "Permission Change",
    "Onboarding": "Onboarding",
    "Receivable": "Receivable",
    "Offboarding": "Offboarding",
    "Reconfiguration": "Reconfiguration",
    "Vending Management": "Vending Management",
    "Change Request": "Change Request",
    "Desktop Support": "Desktop Support"
};
document.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => {
        $(document).ready(function () {
            $("[item-parent='Support']").click(handleItemClick);
        });
    }, 1500);
})

function handleItemClick() {
    let dynamicTitle = $(this).find(".item-anchor").attr("title");

    // Redirect to the 'Issue' list view with the issue_type filter
    if (issuetypes[dynamicTitle]) {
        window.location.href = `/app/issue?issue_type=${issuetypes[dynamicTitle]}`;
    }
}

