"use client";

import styles from "./Modal.module.css";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className={styles.header}>
          <h3>{title}</h3>
          <button className={styles.close} onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </div>
  );
}
