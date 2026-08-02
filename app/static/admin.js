(() => {
  const root = document.documentElement
  const button = document.querySelector("[data-theme-toggle]")
  const readTheme = () => {
    try {
      return localStorage.getItem("md-admin-theme")
    } catch {
      return null
    }
  }
  const storeTheme = theme => {
    try {
      localStorage.setItem("md-admin-theme", theme)
    } catch {
      return
    }
  }
  const stored = readTheme()
  const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
  const applyTheme = theme => {
    root.dataset.theme = theme
    button?.setAttribute("aria-pressed", String(theme === "dark"))
  }
  applyTheme(stored === "dark" || stored === "light" ? stored : preferred)
  button?.addEventListener("click", () => {
    const theme = root.dataset.theme === "dark" ? "light" : "dark"
    storeTheme(theme)
    applyTheme(theme)
  })
})()
