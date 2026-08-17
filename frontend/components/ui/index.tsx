"use client";
import { forwardRef, useEffect, useRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }>(function Button({ className = "", loading, children, ...props }, ref) { return <button ref={ref} className={`button ${className}`} disabled={loading || props.disabled} {...props}>{loading ? "Loading…" : children}</button>; });
export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) { return <section className={`card ${className}`} {...props} />; }
export function Badge({ children, className = "" }: { children: ReactNode; className?: string }) { return <span className={`badge ${className}`}>{children}</span>; }
export function Input(props: InputHTMLAttributes<HTMLInputElement>) { return <input className="search" {...props} />; }
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className="textarea" {...props} />; }
export function Skeleton() { return <div className="skeleton" aria-label="Loading" />; }
export function Spinner() { return <span aria-label="Loading" role="status">⌛</span>; }
export function EmptyState({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function ScrollArea({ children }: { children: ReactNode }) { return <div style={{ overflow: "auto", maxHeight: "70vh" }}>{children}</div>; }
export function Tooltip({ label, children }: { label: string; children: ReactNode }) { return <span title={label}>{children}</span>; }
export function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (!open) return; const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; document.addEventListener("keydown", key); document.body.style.overflow = "hidden"; close.current?.focus(); return () => { document.removeEventListener("keydown", key); document.body.style.overflow = ""; }; }, [open, onClose]);
  if (!open) return null;
  return <div className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={onClose}><div className="modalBox" onMouseDown={(e) => e.stopPropagation()}><div className="row between"><h2>{title}</h2><Button ref={close} className="icon" onClick={onClose} aria-label="Close">×</Button></div>{children}</div></div>;
}
