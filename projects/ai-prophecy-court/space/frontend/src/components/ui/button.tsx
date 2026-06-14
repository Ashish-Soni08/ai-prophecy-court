import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex min-h-11 items-center justify-center gap-2 border border-ink px-4 py-2 font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-acid",
  {
    variants: {
      variant: {
        primary: "bg-acid text-ink shadow-[4px_4px_0_var(--ink)] hover:-translate-y-0.5",
        secondary: "bg-paper-light text-ink hover:bg-acid/15",
        ghost: "border-transparent bg-transparent underline decoration-1 underline-offset-4 hover:text-moss",
        dark: "border-paper-light/30 bg-ink text-paper-light hover:bg-ink/90",
      },
      size: {
        default: "text-sm",
        sm: "min-h-9 px-3 text-xs",
        lg: "min-h-13 px-6 text-base",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
