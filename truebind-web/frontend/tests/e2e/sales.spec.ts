import path from "node:path";
import { expect, test } from "@playwright/test";

const SAMPLE = path.join(__dirname, "..", "..", "public", "demo", "Sample_Bordereau.xlsx");

test("pricing and the sample report are public", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("First file free");
  await expect(page.getByText("Founding pilot").first()).toBeVisible();
  await expect(page.getByText("On request").first()).toBeVisible();
  await page.goto("/demo");
  await expect(page.getByText(/Fix before submitting|Ready to submit/).first()).toBeVisible();
  const res = await page.request.get("/demo/Sample_Bordereau_REVIEWED.xlsx");
  expect(res.status()).toBe(200);
});

test("a visitor sends a bordereau for a free Health Check", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Get a free Health Check" }).first().click();
  const form = page.getByRole("form", { name: "Free Health Check" });
  await form.getByLabel("Full name").fill("Pat Visitor");
  await form.getByLabel("Company").fill("Visitor Coverholder Ltd");
  await form.getByLabel("Work email").fill("pat@visitor.example");
  const send = form.getByRole("button", { name: "Send for a Health Check" });
  await expect(send).toBeDisabled();
  await form.getByLabel(/Your bordereau/).setInputFiles(SAMPLE);
  await expect(send).toBeDisabled(); // consent still needed
  await form.getByRole("checkbox").check();
  await send.click();
  await expect(page.getByText("Your file has arrived safely")).toBeVisible();
});
