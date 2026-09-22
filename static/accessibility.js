(function () {
  "use strict";

  function speak(message) {
    if (!message || !("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));
  }

  function tone(kind) {
    if (!window.AudioContext && !window.webkitAudioContext) return;
    var AudioCtor = window.AudioContext || window.webkitAudioContext;
    var context = new AudioCtor();
    var oscillator = context.createOscillator();
    var gain = context.createGain();
    oscillator.frequency.value = kind === "error" ? 180 : 520;
    gain.gain.value = 0.035;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.06);
  }

  function initializeAccessibility() {
    var prompt = document.body.dataset.speechPrompt;
    var mainInput = document.querySelector("main form input");
    var firstAction = document.querySelector("main nav a, main > a, main > button");
    var announcement = document.querySelector('[role="alert"], [role="status"]');

    if (mainInput) {
      mainInput.focus();
    } else if (firstAction) {
      firstAction.focus();
    }

    speak(announcement ? announcement.textContent.trim() : prompt);

    document.addEventListener("focusin", function (event) {
      var target = event.target;
      if (target.matches("a, button")) {
        speak(target.textContent.trim() + " selected");
      }
    });

    var codeField = document.querySelector('input[inputmode="numeric"]');
    if (codeField) {
      codeField.addEventListener("input", function (event) {
        var value = event.target.value || "";
        var previous = Number(event.target.dataset.length || 0);
        if (value.length > previous) {
          for (var i = previous; i < value.length; i += 1) tone("digit");
        }
        event.target.dataset.length = String(value.length);
      });
      codeField.addEventListener("invalid", function () { tone("error"); }, true);
    }
  }

  window.accessibility = { speak: speak };
  document.addEventListener("DOMContentLoaded", initializeAccessibility);
})();
