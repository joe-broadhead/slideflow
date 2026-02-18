document$.subscribe(function () {
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({
      startOnLoad: true,
      securityLevel: "loose",
      theme: "default",
    });
  }
});
