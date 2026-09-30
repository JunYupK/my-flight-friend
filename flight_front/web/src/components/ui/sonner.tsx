import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

function useDarkClass(): "light" | "dark" {
  const root = document.documentElement
  const [dark, setDark] = useState(() => root.classList.contains("dark"))
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(root.classList.contains("dark")))
    obs.observe(root, { attributes: true, attributeFilter: ["class"] })
    return () => obs.disconnect()
  }, [root])
  return dark ? "dark" : "light"
}

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useDarkClass()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
