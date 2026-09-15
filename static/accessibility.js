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

    if (mainInput) {
      mainInput.focus();
    }

    speak(prompt);
  }

  window.accessibility = { speak: speak };
  document.addEventListener("DOMContentLoaded", initializeAccessibility);
})();