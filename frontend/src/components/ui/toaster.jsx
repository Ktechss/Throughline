import { useToast } from "@/components/ui/use-toast";
import { AlertTriangle, Check } from "lucide-react";
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast";

// Toasts render INSIDE the viewport. They used to be siblings of it — children
// of the provider, which was a second copy of the same fixed container — so the
// viewport was an empty overlay sitting on top of the real one.
export function Toaster() {
  const { toasts, dismiss } = useToast();

  return (
    <ToastProvider>
      <ToastViewport>
        {toasts.map(({ id, title, description, action, variant, ...props }) => {
          const Icon = variant === "destructive" ? AlertTriangle : Check;
          return (
            <Toast key={id} variant={variant} {...props}>
              <Icon
                className={
                  variant === "destructive"
                    ? "h-3.5 w-3.5 shrink-0 mt-0.5 text-rose-300"
                    : "h-3.5 w-3.5 shrink-0 mt-0.5 text-emerald-400"
                }
              />
              <div className="min-w-0 flex-1 grid gap-0.5">
                {title && <ToastTitle>{title}</ToastTitle>}
                {description && <ToastDescription>{description}</ToastDescription>}
              </div>
              {action}
              <ToastClose onClick={() => dismiss(id)} />
            </Toast>
          );
        })}
      </ToastViewport>
    </ToastProvider>
  );
}
