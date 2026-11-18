// The Accounts module is sold as ReckonBooks. Its menu keeps the route name "Accounts SaaS" (so every address
// keeps working); only the heading shown above the menu changes.
(function () {
	const NAMES = ["Accounts SaaS", "Accounts"];
	function rename() {
		document.querySelectorAll(".body-sidebar .header-title").forEach((el) => {
			if (NAMES.includes(el.textContent.trim())) el.textContent = "ReckonBooks";
		});
	}
	$(document).on("startup", () => {
		rename();
		new MutationObserver(rename).observe(document.body, { childList: true, subtree: true });
	});
})();
