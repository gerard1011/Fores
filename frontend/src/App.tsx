import ChatPanel from "./ChatPanel";
import LookupPanel from "./LookupPanel";

function App() {
  return (
    <div className="min-h-screen bg-gray-100 px-4 py-8">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <h1 className="text-2xl font-bold text-gray-900">Boroondara Census Assistant</h1>
        <ChatPanel />
        <LookupPanel />
      </div>
    </div>
  );
}

export default App;
