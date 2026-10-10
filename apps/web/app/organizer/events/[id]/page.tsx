import { OrganizerEditor } from "../../../../components/organizer-editor";
export default async function EditEvent({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OrganizerEditor id={id} />;
}
