"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ROLE_HELP, ROLE_LABEL } from "@/lib/auth";
import { formatDate } from "@/lib/formatters";
import type { InvitationCreated, Role } from "@/lib/types";
import { ErrorState, Modal, Panel, Pill, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const ROLES: Role[] = ["OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER"];

export function MembersSettings({ canManage, myRole, myUserId }: { canManage: boolean; myRole: string; myUserId: string }) {
  const toast = useToast();
  const members = useApi(() => api.listMembers());
  const invitations = useApi(() => (canManage ? api.listInvitations() : Promise.resolve([])), [canManage]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("ANALYST");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const assignable = myRole === "OWNER" ? ROLES : ROLES.filter((r) => r !== "OWNER");

  function fail(title: string, err: unknown) {
    toast({ tone: "bad", title, body: err instanceof ApiError ? err.message : "Please try again." });
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      setCreated(await api.invite(email.trim(), role));
      setEmail("");
      invitations.reload();
    } catch (err) {
      fail("Invitation not created", err);
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(membershipId: string, next: Role) {
    try {
      await api.changeRole(membershipId, next);
      members.reload();
      toast({ tone: "good", title: "Role changed", body: `Now ${ROLE_LABEL[next]}. Recorded in the audit trail.` });
    } catch (err) {
      fail("Role not changed", err);
    }
  }

  async function remove(membershipId: string, who: string) {
    if (!window.confirm(`Remove ${who} from the organisation? They are signed out immediately.`)) return;
    try {
      await api.removeMember(membershipId);
      members.reload();
    } catch (err) {
      fail("Member not removed", err);
    }
  }

  async function revoke(id: string) {
    try {
      await api.revokeInvitation(id);
      invitations.reload();
    } catch (err) {
      fail("Invitation not revoked", err);
    }
  }

  const link = created ? `${window.location.origin}/invite?token=${encodeURIComponent(created.accept_token)}` : "";

  return (
    <>
      {canManage && (
        <Panel title="Invite someone" icon="mail" subtitle="Invitations expire after 7 days. Until e-mail delivery is configured, send the link yourself.">
          <form className={styles.form} onSubmit={invite}>
            <div className={styles.row}>
              <label className={styles.field}>Work e-mail
                <input className={styles.input} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
              </label>
              <div className={styles.field}>
                <label htmlFor="invite-role">Role</label>
                <select id="invite-role" className={styles.select} value={role} onChange={(e) => setRole(e.target.value as Role)} aria-describedby="role-help">
                  {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </div>
            </div>
            <p id="role-help" className={styles.help}>{ROLE_HELP[role]}</p>
            <div className={styles.actions}><Button type="submit" loading={busy}>Create invitation</Button></div>
          </form>
        </Panel>
      )}

      <Panel title="Members" icon="user" flush subtitle="Roles decide what each person can see and do; every change is audited.">
        {members.error ? <ErrorState message={members.error} onRetry={members.reload} /> : !members.data ? <SkeletonRows rows={3} /> : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th scope="col">Person</th><th scope="col">Role</th><th scope="col">Joined</th>{canManage && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
              <tbody>
                {members.data.map((m) => {
                  const locked = !canManage || (m.role === "OWNER" && myRole !== "OWNER");
                  return (
                    <tr key={m.membership_id}>
                      <td><div className={styles.who}><strong>{m.display_name}{m.user_id === myUserId ? " (you)" : ""}</strong><span>{m.email}</span></div></td>
                      <td>
                        {locked ? <Pill tone={m.role === "OWNER" ? "brand" : "neutral"}>{ROLE_LABEL[m.role] ?? m.role}</Pill> : (
                          <select className={styles.select} value={m.role} aria-label={`Role for ${m.email}`}
                            onChange={(e) => changeRole(m.membership_id, e.target.value as Role)}>
                            {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                          </select>
                        )}
                      </td>
                      <td>{formatDate(m.created_at)}</td>
                      {canManage && <td>{!locked && <Button variant="ghost" size="sm" onClick={() => remove(m.membership_id, m.email)}>Remove</Button>}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {canManage && invitations.data && invitations.data.length > 0 && (
        <Panel title="Pending invitations" icon="clock" flush>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th scope="col">E-mail</th><th scope="col">Role</th><th scope="col">Expires</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {invitations.data.map((i) => (
                  <tr key={i.id}>
                    <td>{i.email}</td><td>{ROLE_LABEL[i.role]}</td><td>{formatDate(i.expires_at)}</td>
                    <td><Button variant="ghost" size="sm" onClick={() => revoke(i.id)}>Revoke</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Modal open={created !== null} onClose={() => setCreated(null)} title="Invitation created"
        footer={<Button onClick={() => { void navigator.clipboard?.writeText(link); toast({ tone: "good", title: "Link copied" }); }}>Copy link</Button>}>
        <p className={styles.muted}>Send this link to {created?.email}. It works once and expires on {created ? formatDate(created.expires_at) : ""}. It is shown only now.</p>
        <p className={styles.codeBox} data-testid="invite-link">{link}</p>
      </Modal>
    </>
  );
}
