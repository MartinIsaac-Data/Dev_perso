import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { Separator } from "@/components/ui/separator";
import { ProfileForm, type ProfileFormInitialValues } from "@/app/(app)/settings/profile-form";
import { DangerZone } from "@/app/(app)/settings/danger-zone";

function toDateInputValue(date: Date | null | undefined) {
  if (!date) return "";
  return date.toISOString().slice(0, 10);
}

export default async function SettingsPage() {
  const userId = await requireUserId();
  const profile = await prisma.profile.findUnique({ where: { userId } });

  const initialValues: ProfileFormInitialValues = {
    fullName: profile?.fullName ?? "",
    currentLocation: profile?.currentLocation ?? "",
    dateOfBirth: toDateInputValue(profile?.dateOfBirth),
    currentJobTitle: profile?.currentJobTitle ?? "",
    currentCompany: profile?.currentCompany ?? "",
    yearsOfExperience: profile?.yearsOfExperience?.toString() ?? "",
    languages: profile?.languages.join(", ") ?? "",
    careerGoalShortTerm: profile?.careerGoalShortTerm ?? "",
    careerGoalLongTerm: profile?.careerGoalLongTerm ?? "",
    mbaRationale: profile?.mbaRationale ?? "",
    mbaTargetYear: profile?.mbaTargetYear?.toString() ?? "",
    professionalInterests: profile?.professionalInterests.join(", ") ?? "",
    currency: profile?.currency ?? "EUR",
    timezone: profile?.timezone ?? "Europe/Paris",
    appMode: profile?.appMode ?? "PRE_MBA",
  };

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Everything here is editable — nothing about your profile is hard-coded."
      />
      <div className="flex max-w-2xl flex-col gap-6">
        <ProfileForm initialValues={initialValues} />
        <Separator />
        <DangerZone />
      </div>
    </div>
  );
}
