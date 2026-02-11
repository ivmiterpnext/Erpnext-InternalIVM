let issuetypes = {
    "IT": "IT",
    "Permission Change": "Permission Change",
    "Onboarding": "Onboarding",
    "Receivable": "Receivable",
    "Offboarding": "Offboarding",
    "Reconfiguration": "Reconfiguration",
    "Vending Management": "Vending Management",
    "Change Request": "Change Request",
    "Desktop Support": "Desktop Support",
    "Support Queue": "Support Queue"
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
    if (issuetypes[dynamicTitle] == "Support Queue") {
        let support = dynamicTitle.substring(0, 7)
        window.location.href = `/app/issue?issue_type=${support}`;
    }
    else {
        window.location.href = `/app/issue?issue_type=${issuetypes[dynamicTitle]}`;
    }
}

