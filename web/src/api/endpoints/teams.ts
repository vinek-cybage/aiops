import { apiJson } from "../client";
import type { AuthUser } from "../../auth/types";

export interface Team {
  id: number;
  name: string;
  services: string[];
  org_id: string;
}

export interface TeamMember {
  user_id: number;
  name: string;
  email: string;
  org_role: string;
  team_role: "team_admin" | "member";
  is_active: boolean;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
}

export interface InvitationPreview {
  email: string;
  org_name: string | null;
  team_name: string | null;
  team_role: string;
}

export function listTeams(): Promise<Team[]> {
  return apiJson("/api/teams");
}

export function createTeam(name: string, services: string[] = []): Promise<Team> {
  return apiJson("/api/teams", {
    method: "POST",
    body: JSON.stringify({ name, services }),
  });
}

export function listMembers(teamId: number): Promise<TeamMember[]> {
  return apiJson(`/api/teams/${teamId}/members`);
}

export function updateMemberRole(teamId: number, userId: number, teamRole: string): Promise<TeamMember> {
  return apiJson(`/api/teams/${teamId}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ team_role: teamRole }),
  });
}

export function removeMember(teamId: number, userId: number): Promise<void> {
  return apiJson(`/api/teams/${teamId}/members/${userId}`, { method: "DELETE" });
}

export function listInvitations(teamId: number): Promise<Invitation[]> {
  return apiJson(`/api/teams/${teamId}/invitations`);
}

export function createInvitation(
  teamId: number,
  email: string,
  teamRole: string,
): Promise<{ id: string; email: string; team_role: string; invite_link: string }> {
  return apiJson(`/api/teams/${teamId}/invitations`, {
    method: "POST",
    body: JSON.stringify({ email, team_role: teamRole }),
  });
}

export function revokeInvitation(teamId: number, invitationId: string): Promise<void> {
  return apiJson(`/api/teams/${teamId}/invitations/${invitationId}`, { method: "DELETE" });
}

export function previewInvitation(token: string): Promise<InvitationPreview> {
  return apiJson(`/api/auth/invitations/${token}`);
}

export function acceptInvitation(
  token: string,
  name: string,
  password: string,
): Promise<{ access_token: string; user: AuthUser }> {
  return apiJson(`/api/auth/invitations/${token}/accept`, {
    method: "POST",
    body: JSON.stringify({ name, password }),
  });
}
