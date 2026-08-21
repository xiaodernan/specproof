import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  fullWidth?: boolean;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(props, ref) {
    const {
      variant = "secondary",
      size = "md",
      loading = false,
      fullWidth = false,
      disabled,
      className,
      children,
      type = "button",
      onClick,
      ...rest
    } = props;

    const cls = [
      "ui-btn",
      "ui-btn-" + variant,
      "ui-btn-" + size,
      fullWidth ? "ui-btn-block" : "",
      className ?? "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <button
        ref={ref}
        type={type}
        className={cls}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        onClick={onClick}
        {...rest}
      >
        {loading ? <span className="ui-btn-spinner" aria-hidden="true" /> : null}
        {children}
      </button>
    );
  }
);
