"use client";

import { useRef, useState } from "react";
import styles from "./FileUpload.module.css";

export function FileUpload({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  return (
    <div
      className={`${styles.dropzone} ${dragOver ? styles.dragOver : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <p className={styles.text}>Drop a workbook to begin</p>
      <p className={styles.hint}>XLSX, XLSM or CSV · multi-sheet supported</p>
      <button
        type="button"
        className={styles.browseButton}
        onClick={() => inputRef.current?.click()}
        disabled={busy}
      >
        {busy ? "Uploading…" : "Choose file"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xlsm,.xls,.csv"
        className={styles.hiddenInput}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
