import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');
const activeDialogs: HTMLElement[] = [];
let dialogScrollLockCount = 0;
let bodyOverflowBeforeDialogs = '';

const lockBodyScroll = (): void => {
  if (dialogScrollLockCount === 0) bodyOverflowBeforeDialogs = document.body.style.overflow;
  dialogScrollLockCount += 1;
  document.body.style.overflow = 'hidden';
};

const unlockBodyScroll = (): void => {
  dialogScrollLockCount = Math.max(0, dialogScrollLockCount - 1);
  if (dialogScrollLockCount === 0) document.body.style.overflow = bodyOverflowBeforeDialogs;
};

interface DialogInteractionsOptions {
  open: boolean;
  dialogRef: RefObject<HTMLElement | null>;
  onEscape?: () => void;
  initialFocusSelector?: string;
  returnFocusRef?: RefObject<HTMLElement | null>;
}

const getFocusableElements = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true'
  );

export const useDialogInteractions = ({
  open,
  dialogRef,
  onEscape,
  initialFocusSelector,
  returnFocusRef,
}: DialogInteractionsOptions): void => {
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const onEscapeRef = useRef(onEscape);

  useEffect(() => {
    onEscapeRef.current = onEscape;
  }, [onEscape]);

  useEffect(() => {
    if (!open) return;

    previousActiveElement.current = document.activeElement as HTMLElement;
    const returnFocusElement = returnFocusRef?.current ?? previousActiveElement.current;
    lockBodyScroll();

    const dialog = dialogRef.current;
    if (dialog) activeDialogs.push(dialog);
    const preferred = initialFocusSelector
      ? dialog?.querySelector<HTMLElement>(initialFocusSelector)
      : null;
    const focusableElements = dialog ? getFocusableElements(dialog) : [];
    (preferred ?? focusableElements[0] ?? dialog)?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!dialog || activeDialogs[activeDialogs.length - 1] !== dialog) return;
      if (event.key === 'Escape') {
        onEscapeRef.current?.();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;

      const currentDialog = dialogRef.current;
      const currentFocusableElements = getFocusableElements(currentDialog);
      if (currentFocusableElements.length === 0) {
        event.preventDefault();
        currentDialog.focus();
        return;
      }

      const first = currentFocusableElements[0];
      const last = currentFocusableElements[currentFocusableElements.length - 1];
      const activeElement = document.activeElement;

      if (event.shiftKey && (activeElement === first || !currentDialog.contains(activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (activeElement === last || !currentDialog.contains(activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (dialog) {
        const dialogIndex = activeDialogs.lastIndexOf(dialog);
        if (dialogIndex >= 0) activeDialogs.splice(dialogIndex, 1);
      }
      unlockBodyScroll();
      returnFocusElement?.focus();
    };
  }, [dialogRef, initialFocusSelector, open, returnFocusRef]);
};
