import type { NextAuthConfig } from "next-auth";

// Edge-safe config: no Node-only dependencies (bcrypt, pg) may be imported
// from this file, since middleware.ts loads it directly.
export const authConfig = {
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  callbacks: {
    jwt: ({ token, user }) => {
      if (user) token.id = user.id;
      return token;
    },
    session: ({ session, token }) => {
      if (session.user && token.id) {
        session.user.id = token.id as string;
      }
      return session;
    },
  },
  providers: [],
} satisfies NextAuthConfig;
