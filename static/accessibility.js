(function () {
  "use strict";

  function speak(message) {
    if (!message || !("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));
  }

  function initializeAccessibility() {
    var prompt = document.body.dataset.speechPrompt;
    var mainInput = document.querySelector("main form input");
    var announcement = document.querySelector('[role="alert"], [role="status"]');

    if (mainInput) {
      mainInput.focus();
    }

    speak(announcement ? announcement.textContent.trim() : prompt);
  }

  window.accessibility = { speak: speak };
  document.addEventListener("DOMContentLoaded", initializeAccessibility);
})();
