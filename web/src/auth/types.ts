export interface AuthUser {
  id: number;
  email: string;
  name: string;
  role: "platform_admin" | "org_admin" | "member";
  org_id: string;
}
