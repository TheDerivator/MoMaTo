// Entry point of the browser app: mounts the application into #app.
import { mount } from "./app.js";

const container = document.getElementById("app");
if (container) {
  container.textContent = "";
  mount(container);
}
